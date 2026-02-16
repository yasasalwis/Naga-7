import asyncio
import logging
import json
from google.protobuf.json_format import MessageToDict, Parse
from ..service_manager.base_service import BaseService
from ..messaging.nats_client import nats_client
from ..config import settings
from ..database.session import async_session_maker
# Import generated protobuf class
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

    async def start(self):
        self._running = True
        logger.info("EventPipelineService started.")
        
        # Subscribe to Sentinel events
        if nats_client.nc.is_connected:
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

    async def handle_event(self, msg):
        """
        Callback for incoming NATS messages (Protobuf).
        """
        try:
            # Parse Protobuf
            proto_event = ProtoEvent()
            proto_event.ParseFromString(msg.data)
            
            logger.info(f"Received event: {proto_event.event_id} from {proto_event.sentinel_id} type={proto_event.event_class}")
            
            # Convert to dict for easier handling/enrichment
            event_dict = MessageToDict(proto_event, preserving_proto_field_name=True)
            
            # TODO: Persist to DB (TimescaleDB)
            # async with async_session_maker() as session:
            #     db_event = EventModel(**event_dict)
            #     session.add(db_event)
            #     await session.commit()
            
            # For now just log
            logger.debug(f"Event data: {event_dict}")
            
            # Forward to Threat Correlator?
            # In TDD: Pipeline publishes to Correlator (via NATS "n7.alerts" or internal queue?).
            # Internal function call might be simpler for MVP, but decoupling via NATS is better.
            # Let's publish to internal subject for correlation?
            # await nats_client.nc.publish("n7.internal.events", msg.data)

        except Exception as e:
            logger.error(f"Error processing event: {e}")
