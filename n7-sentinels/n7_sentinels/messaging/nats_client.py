import logging
import ssl
from pathlib import Path
from typing import Optional

from nats.aio.client import Client as NATS

from ..agent_runtime.config import settings

logger = logging.getLogger("n7-sentinel.messaging")

# agent_certs/ is written at the n7-sentinels package root (one level above n7_sentinels/)
_AGENT_CERTS = Path(__file__).parent.parent.parent / "agent_certs"


def _build_tls_context() -> Optional[ssl.SSLContext]:
    """
    Build an mTLS SSL context from certs provisioned at registration time.
    - ca.crt   : received from Core at registration; used to verify the NATS server cert
    - client.crt/key : agent's identity cert, also received from Core
    Returns None if certs haven't been provisioned yet (pre-registration state).
    """
    cert_path = _AGENT_CERTS / "client.crt"
    key_path  = _AGENT_CERTS / "client.key"
    ca_path   = _AGENT_CERTS / "ca.crt"

    if not (cert_path.exists() and key_path.exists()):
        return None

    if ca_path.exists():
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH, cafile=str(ca_path))
    else:
        logger.warning("agent_certs/ca.crt missing — falling back to system trust store")
        ctx = ssl.create_default_context(ssl.Purpose.SERVER_AUTH)

    ctx.check_hostname = False  # NATS server cert SAN is 'localhost', not a hostname
    ctx.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
    return ctx


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
        Enforces mTLS using certs provisioned by Core at registration time.
        """
        tls_ctx = _build_tls_context()
        if tls_ctx:
            logger.info("Using mTLS for NATS connection")

        try:
            await self.nc.connect(
                servers=[settings.NATS_URL],
                tls=tls_ctx,
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
