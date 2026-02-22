import asyncio
import json
import logging
import uuid
from collections import deque

from nats.aio.client import Client as NATS

from .config import settings
from ..agent_id import get_agent_id
from ..messaging.nats_client import _build_tls_context

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
        self.js = None
        self._buffer = deque(maxlen=1000)
        self._flush_task = None

    async def start(self):
        self._running = True
        logger.info("EventEmitterService started.")

        try:
            tls_ctx = _build_tls_context()
            if tls_ctx:
                logger.info("Using mTLS for NATS (JetStream) connection")
            # Connect options with reconnect logic
            await self.nc.connect(
                servers=[settings.NATS_URL],
                tls=tls_ctx,
                reconnect_time_wait=2,
                max_reconnect_attempts=-1
            )
            self.js = self.nc.jetstream()
            logger.info(f"Connected to NATS at {settings.NATS_URL} with JetStream.")
        except Exception as e:
            logger.error(f"Failed to connect to NATS initially: {e}")
            # Continue running to allow buffering

        self._flush_task = asyncio.create_task(self._flush_loop())

    async def stop(self):
        self._running = False
        if self._flush_task:
            self._flush_task.cancel()
            try:
                await self._flush_task
            except asyncio.CancelledError:
                pass

        if self.nc.is_connected:
            await self.nc.drain()
        logger.info("EventEmitterService stopped.")

    async def _flush_loop(self):
        """
        Periodically attempts to flush the buffer to NATS via JetStream.
        """
        while self._running:
            if self.nc.is_connected and self.js and self._buffer:
                logger.info(f"Flushing {len(self._buffer)} buffered events...")
                while self._buffer:
                    if not self.nc.is_connected:
                        break  # Stop flushing if connection lost

                    event_data = self._buffer[0]  # Peek
                    try:
                        subject = f"n7.events.{settings.AGENT_TYPE}.{settings.AGENT_SUBTYPE}"
                        payload = json.dumps(event_data).encode()
                        await self.js.publish(subject, payload)
                        self._buffer.popleft()  # Remove only after successful publish (or at least sent)
                    except Exception as e:
                        logger.error(f"Failed to flush event: {e}")
                        await asyncio.sleep(1)  # Backoff on error
                        break

            await asyncio.sleep(1)  # Check every second

    def _stamp(self, event_data: dict) -> dict:
        """Inject sentinel_id and event_id if not already present."""
        event = dict(event_data)
        event.setdefault("sentinel_id", get_agent_id())
        event.setdefault("event_id", str(uuid.uuid4()))
        return event

    async def emit(self, event_data: dict):
        """
        Publishes an event to NATS via JetStream or buffers it.
        """
        event_data = self._stamp(event_data)
        if not self.nc.is_connected or not self.js:
            if self._buffer.maxlen and len(self._buffer) < self._buffer.maxlen:
                self._buffer.append(event_data)
                logger.warning(f"NATS/JetStream not connected. Buffered event. Buffer size: {len(self._buffer)}")
            elif self._buffer.maxlen is None:  # Should not happen with maxlen=1000 but for type safety
                self._buffer.append(event_data)
            else:
                logger.error("Buffer full! Dropping event.")
            return

        try:
            subject = f"n7.events.{settings.AGENT_TYPE}.{settings.AGENT_SUBTYPE}"
            payload = json.dumps(event_data).encode()
            # Awaiting js.publish ensures JetStream received and stored the event
            await self.js.publish(subject, payload)
        except Exception as e:
            logger.error(f"Failed to emit event: {e}")
            # Try to buffer if publish failed
            if self._buffer.maxlen and len(self._buffer) < self._buffer.maxlen:
                self._buffer.append(event_data)
