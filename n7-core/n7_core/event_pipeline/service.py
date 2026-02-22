import asyncio
import hashlib
import json
import logging
from datetime import datetime

from schemas.events_pb2 import Event as ProtoEvent
from ..database.redis import redis_client
from ..database.session import async_session_maker
from ..messaging.nats_client import nats_client
from ..models.event import Event as EventModel
from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.event-pipeline")


class EventPipelineService(BaseService):
    """
    Event Pipeline Service.
    Responsibility: Ingest, validate, normalize, deduplicate, and enrich events from Sentinels.
    """

    def __init__(self):
        super().__init__("EventPipelineService")
        self._running = False
        self.dedup_window = 60  # seconds
        self.enrichment_service = None  # Injected via set_enrichment_service()
        self._buffer: list = []
        self._flush_lock = asyncio.Lock()
        self._flush_task: asyncio.Task | None = None
        self.FLUSH_INTERVAL = 1.0    # seconds
        self.FLUSH_BATCH_SIZE = 500  # items

    def set_enrichment_service(self, enrichment_service):
        """Inject EnrichmentService (which in turn holds ThreatIntelService)."""
        self.enrichment_service = enrichment_service

    async def start(self):
        self._running = True
        logger.info("EventPipelineService started.")

        # Subscribe to Sentinel events via JetStream
        if nats_client.nc and nats_client.nc.is_connected and nats_client.js:
            try:
                await nats_client.js.subscribe(
                    "n7.events.>",
                    cb=self.handle_event,
                    durable="event_pipeline_durable",
                )
                logger.info("Subscribed to JetStream n7.events.> (durable: event_pipeline_durable)")
            except Exception as e:
                logger.error(f"Failed to subscribe to JetStream: {e}")
        else:
            logger.warning("NATS/JetStream not connected, EventPipelineService waiting for connection...")

        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self):
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass
        await self._flush_buffer()  # drain remaining events
        logger.info("EventPipelineService stopped.")

    async def _flush_loop(self):
        while self._running:
            await asyncio.sleep(self.FLUSH_INTERVAL)
            await self._flush_buffer()

    async def _flush_buffer(self):
        async with self._flush_lock:
            if not self._buffer:
                return
            batch = self._buffer[:]
            self._buffer.clear()
        async with async_session_maker() as session:
            session.add_all(batch)
            await session.commit()
        logger.debug(f"Flushed {len(batch)} events to DB.")

    async def _is_duplicate(self, event_dict: dict) -> bool:
        """
        Check if event is a duplicate using Redis.
        Key: sentinel_type:event_class:hash(raw_data)
        """
        try:
            # Create a deterministic hash of the event content
            # Avoiding timestamp in hash as duplicate events might have slightly different timestamps
            # Use raw_data and sentinel_id
            unique_str = f"{event_dict.get('sentinel_id')}:{event_dict.get('event_class')}:{json.dumps(event_dict.get('raw_data'), sort_keys=True)}"
            event_hash = hashlib.sha256(unique_str.encode()).hexdigest()
            key = f"n7:dedup:{event_hash}"

            # Check if key exists
            if await redis_client.get(key):
                return True

            # Set key with expiry
            await redis_client.set(key, "1", ex=self.dedup_window)
            return False
        except Exception as e:
            logger.error(f"Redis error in deduplication: {e}")
            return False  # Fail open (allow potential duplicates rather than dropping)

    async def handle_event(self, msg):
        """
        Callback for incoming NATS messages (JSON from EventEmitterService).
        """
        try:
            # Parse JSON payload sent by EventEmitterService
            event_dict = json.loads(msg.data.decode())

            import uuid as _uuid
            event_id = event_dict.get("event_id") or str(_uuid.uuid4())
            # Ensure event_id is a valid UUID string; generate one if malformed
            try:
                _uuid.UUID(str(event_id))
            except (ValueError, AttributeError):
                event_id = str(_uuid.uuid4())

            # sentinel_id must be a valid UUID for the DB column; fall back to a
            # deterministic nil-UUID so rows still persist rather than crashing.
            _raw_sentinel_id = event_dict.get("sentinel_id", "")
            try:
                sentinel_id = str(_uuid.UUID(str(_raw_sentinel_id)))
            except (ValueError, AttributeError):
                sentinel_id = str(_uuid.UUID(int=0))  # 00000000-0000-0000-0000-000000000000

            event_class = event_dict.get("event_class", "unknown")
            severity = event_dict.get("severity", "informational")
            raw_data = event_dict.get("raw_data", {})
            if isinstance(raw_data, str):
                try:
                    raw_data = json.loads(raw_data)
                except Exception:
                    raw_data = {"raw": raw_data}
            timestamp_str = event_dict.get("timestamp")

            # 1. Deduplication
            if await self._is_duplicate(event_dict):
                logger.debug(f"Duplicate event dropped: {event_id}")
                return

            logger.info(f"Processing event: {event_id} type={event_class}")

            # 2. Enrichment — IOC cross-reference via ThreatIntelService
            enrichments = {}
            if self.enrichment_service:
                enrichments = await self.enrichment_service.enrich_event(event_dict)

            # IOC Promotion: if any IOC match found, immediately elevate event to critical
            if enrichments.get("threat_intel_matches"):
                logger.warning(
                    f"IOC match on event {event_id} — promoting to critical. "
                    f"Matches: {enrichments['threat_intel_matches']}"
                )
                severity = "critical"
                raw_data["ioc_matched"] = True
                raw_data["ioc_matches"] = enrichments["threat_intel_matches"]

            # 3. Persistence — push to buffer for batch flush
            ts = datetime.utcnow()
            if timestamp_str:
                try:
                    ts = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                except Exception:
                    pass

            db_event = EventModel(
                event_id=event_id,
                timestamp=ts,
                sentinel_id=sentinel_id,
                event_class=event_class,
                severity=severity,
                raw_data=raw_data,
                enrichments=enrichments,
                mitre_techniques=event_dict.get("mitre_techniques", [])
            )
            self._buffer.append(db_event)
            if len(self._buffer) >= self.FLUSH_BATCH_SIZE:
                asyncio.create_task(self._flush_buffer())

            # 4. Forward to Threat Correlation (via NATS subject) as Protobuf
            if nats_client.nc and nats_client.nc.is_connected:
                proto_event = ProtoEvent(
                    event_id=event_id,
                    timestamp=ts.isoformat(),
                    sentinel_id=sentinel_id,
                    event_class=event_class,
                    severity=severity,
                    raw_data=json.dumps(raw_data),
                    enrichments=json.dumps(enrichments),
                )
                await nats_client.nc.publish("n7.internal.events", proto_event.SerializeToString())

        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
