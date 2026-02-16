
import asyncio
import logging
import json
from nats.aio.client import Client as NATS
from .config import settings

logger = logging.getLogger("n7-sentinel.event-emitter")

class EventEmitterService:
    """
    Event Emitter Service.
    Responsibility: Buffer and send events to Core via NATS.
    Ref: TDD Section 5.1 Sentinel Process Model
    """
    def __init__(self):
        self._running = False
        self.nc = NATS()

    async def start(self):
        self._running = True
        logger.info("EventEmitterService started.")
        
        try:
            await self.nc.connect(servers=[settings.NATS_URL])
            logger.info(f"Connected to NATS at {settings.NATS_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")

    async def stop(self):
        self._running = False
        if self.nc.is_connected:
            await self.nc.drain()
        logger.info("EventEmitterService stopped.")

    async def emit(self, event_data: dict):
        """
        Publishes an event to NATS.
        """
        if not self.nc.is_connected:
            logger.warning("NATS not connected, dropping event (TODO: Buffer)")
            return

        try:
            subject = f"n7.events.{settings.AGENT_TYPE}.{settings.AGENT_SUBTYPE}"
            payload = json.dumps(event_data).encode()
            await self.nc.publish(subject, payload)
        except Exception as e:
            logger.error(f"Failed to emit event: {e}")
