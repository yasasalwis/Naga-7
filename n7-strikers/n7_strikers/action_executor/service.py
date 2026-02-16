
import asyncio
import logging
import json
from nats.aio.client import Client as NATS
from .config import settings

logger = logging.getLogger("n7-striker.action-executor")

class ActionExecutorService:
    """
    Action Executor Service.
    Responsibility: Listen for commands and execute response actions.
    Ref: TDD Section 6.1 Striker Process Model
    """
    def __init__(self):
        self._running = False
        self.nc = NATS()

    async def start(self):
        self._running = True
        logger.info("ActionExecutorService started.")
        
        try:
            await self.nc.connect(servers=[settings.NATS_URL])
            logger.info(f"Connected to NATS at {settings.NATS_URL}")
            
            # Subscribe to commands for this agent
            subject = f"n7.commands.{settings.AGENT_ZONE}.{settings.AGENT_SUBTYPE}.>"
            await self.nc.subscribe(subject, cb=self.handle_command)
            logger.info(f"Subscribed to {subject}")
            
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")

    async def stop(self):
        self._running = False
        if self.nc.is_connected:
            await self.nc.drain()
        logger.info("ActionExecutorService stopped.")

    async def handle_command(self, msg):
        """
        Callback for incoming commands.
        """
        try:
            command = json.loads(msg.data.decode())
            logger.info(f"Received command: {command}")
            
            # Execute action
            # ...
            
        except Exception as e:
            logger.error(f"Error handling command: {e}")
