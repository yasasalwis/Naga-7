
import asyncio
import logging
import json
from ..service_manager.base_service import BaseService
from ..messaging.nats_client import nats_client
from ..schemas.event import Event
from ..config import settings

logger = logging.getLogger("n7-core.event-pipeline")

class EventPipelineService(BaseService):
    """
    Event Pipeline Service.
    Responsibility: Ingest, validate, normalize, deduplicate, and enrich events from Sentinels.
    Ref: TDD Section 4.2 Event Pipeline Service
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
                queue="event_pipeline" # Queue group for load balancing
            )
            logger.info("Subscribed to n7.events.>")
        else:
            logger.warning("NATS not connected, EventPipelineService waiting for connection...")

    async def stop(self):
        self._running = False
        logger.info("EventPipelineService stopped.")

    async def handle_event(self, msg):
        """
        Callback for incoming NATS messages.
        """
        try:
            data = json.loads(msg.data.decode())
            # Validate against schema
            event = Event(**data)
            
            logger.info(f"Received event: {event.event_id} from {event.sentinel_id}")
            
            # TODO: Normalization
            # TODO: Deduplication
            # TODO: Enrichment
            # TODO: Persistence
            # TODO: Publish to Threat Correlator

        except json.JSONDecodeError:
            logger.error("Failed to decode event JSON")
        except Exception as e:
            logger.error(f"Error processing event: {e}")
