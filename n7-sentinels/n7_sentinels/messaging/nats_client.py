import logging

from nats.aio.client import Client as NATS

from ..agent_runtime.config import settings

logger = logging.getLogger("n7-sentinel.messaging")


class NATSClient:
    """
    NATS Client wrapper for Sentinel agents.
    Provides connection management and auto-reconnect support.
    Used for push-based heartbeats (n7.heartbeat.sentinel.{agent_id})
    and node metadata publish (n7.node.metadata.{agent_id}).
    """

    def __init__(self):
        self.nc = NATS()

    async def connect(self):
        """
        Connects to the NATS cluster with resilience settings.
        """
        try:
            await self.nc.connect(
                servers=[settings.NATS_URL],
                reconnect_time_wait=2,
                max_reconnect_attempts=-1,  # Infinite reconnects
                error_cb=self._error_cb,
                disconnected_cb=self._disconnected_cb,
                reconnected_cb=self._reconnected_cb,
            )
            logger.info(f"Connected to NATS at {settings.NATS_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")
            raise

    async def close(self):
        """
        Gracefully closes the NATS connection.
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
