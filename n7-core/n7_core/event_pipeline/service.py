import asyncio
import logging
import json
import hashlib
from datetime import datetime, timedelta
from google.protobuf.json_format import MessageToDict
from sqlalchemy.ext.asyncio import AsyncSession

from ..service_manager.base_service import BaseService
from ..messaging.nats_client import nats_client
from ..config import settings
from ..database.session import async_session_maker
from ..database.redis import redis_client
from ..models.event import Event as EventModel
# Protobuf schemas generated successfully
from schemas.events_pb2 import Event as ProtoEvent
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
        self.dedup_window = 60 # seconds

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
            return False # Fail open (allow potential duplicates rather than dropping)

    async def handle_event(self, msg):
        """
        Callback for incoming NATS messages (Protobuf).
        """
        try:
            # Parse Protobuf
            proto_event = ProtoEvent()
            proto_event.ParseFromString(msg.data)
            
            event_dict = MessageToDict(proto_event, preserving_proto_field_name=True)
            
            # 1. Deduplication
            if await self._is_duplicate(event_dict):
                logger.debug(f"Duplicate event dropped: {proto_event.event_id}")
                return

            logger.info(f"Processing event: {proto_event.event_id} type={proto_event.event_class}")

            # 2. Enrichment (Placeholder for now)
            enrichments = {}
            # e.g., enrichments['geo_ip'] = lookup_ip(event_dict['raw_data']['source_ip'])

            # 3. Persistence
            async with async_session_maker() as session:
                # Handle timestamp: Proto timestamp is usually string ISO 8601 or Google Timestamp
                # Assuming string for simplicity based on previous context, or current time fallback
                ts = datetime.utcnow()
                if hasattr(proto_event, 'timestamp') and proto_event.timestamp:
                     try:
                         ts = datetime.fromisoformat(proto_event.timestamp.replace('Z', '+00:00'))
                     except:
                         pass

                db_event = EventModel(
                    event_id=proto_event.event_id,
                    timestamp=ts,
                    sentinel_id=proto_event.sentinel_id,
                    event_class=proto_event.event_class,
                    severity=proto_event.severity,
                    raw_data=event_dict.get('raw_data', {}),
                    enrichments=enrichments,
                    mitre_techniques=list(proto_event.mitre_techniques) if hasattr(proto_event, 'mitre_techniques') else []
                )
                session.add(db_event)
                await session.commit()
            
            # 4. Forward to Threat Correlation (via NATS subject)
            # Publishing to internal stream for other services (Correlator)
            if nats_client.nc:
                await nats_client.nc.publish("n7.internal.events", msg.data)

        except Exception as e:
            logger.error(f"Error processing event: {e}", exc_info=True)
