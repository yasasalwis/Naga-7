import logging

from nats.aio.client import Client as NATS
from nats.js import JetStreamContext

from ..config import settings

logger = logging.getLogger("n7-core.messaging")


class NATSClient:
    """
    NATS Client wrapper with auto-reconnect and JetStream support.
    Ref: TDD Section 3.1 & 7.1
    """

    def __init__(self):
        self.nc = NATS()
        self.js: Optional[JetStreamContext] = None

    async def connect(self):
        """
        Connects to NATS cluster with resilience settings.
        """
        try:
            await self.nc.connect(
                servers=[settings.NATS_URL],
                name=settings.NATS_CLIENT_ID,
                reconnect_time_wait=2,
                max_reconnect_attempts=-1,  # Infinite reconnects
                error_cb=self._error_cb,
                disconnected_cb=self._disconnected_cb,
                reconnected_cb=self._reconnected_cb,
            )
            self.js = self.nc.jetstream()
            logger.info(f"Connected to NATS at {settings.NATS_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")
            raise

    async def close(self):
        """
         gracefully closes the NATS connection.
        """
        if self.nc.is_connected:
            await self.nc.drain()
            logger.info("NATS connection closed.")

    async def _error_cb(self, e):
        logger.error(f"NATS Error: {e}")

    async def _disconnected_cb(self):
        logger.warning("Disconnected from NATS...")

    async def _reconnected_cb(self):
        logger.info("Reconnected to NATS!")


nats_client = NATSClient()
