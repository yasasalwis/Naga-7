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

# Import models
# We don't have an Event model yet? The TDD says "Persist all raw and enriched events to a time-series data store".
# I should create an Event model in models/event.py? Or just use a raw execution for TimescaleDB.
# For simplicity and speed, let's assume we create an Event model or just log it for now.
# Wait, I should create the Event model first? Yes.
# But I am in the middle of this file creation.
# I'll add a TODO or basic logging, then fix model.
# Actually I'll use raw SQL or just not save purely yet? 
# No, let's do it right. I'll import a (to be created) Event model.
# from ..models.event import EventModel

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

    def set_enrichment_service(self, enrichment_service):
        """Inject EnrichmentService (which in turn holds ThreatIntelService)."""
        self.enrichment_service = enrichment_service

    async def start(self):
        self._running = True
        logger.info("EventPipelineService started.")

        # Subscribe to Sentinel events
        if nats_client.nc and nats_client.nc.is_connected:
            await nats_client.nc.subscribe(
                "n7.events.>",
                cb=self.handle_event,
                queue="event_pipeline"
            )
            logger.info("Subscribed to n7.events.>")
        else:
            logger.warning("NATS not connected, EventPipelineService waiting for connection...")

    async def stop(self):
        self._running = False
        logger.info("EventPipelineService stopped.")

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

            event_id = event_dict.get("event_id", str(__import__("uuid").uuid4()))
            sentinel_id = event_dict.get("sentinel_id", "unknown")
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

            # 3. Persistence
            async with async_session_maker() as session:
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
                session.add(db_event)
                await session.commit()

            # 4. Forward to Threat Correlation (via NATS subject) as Protobuf
            if nats_client.nc:
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
