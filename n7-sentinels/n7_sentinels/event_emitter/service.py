
import asyncio
import logging
import json
from collections import deque
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
        self._buffer = deque(maxlen=1000)
        self._flush_task = None

    async def start(self):
        self._running = True
        logger.info("EventEmitterService started.")
        
        try:
            # Connect options with reconnect logic
            await self.nc.connect(
                servers=[settings.NATS_URL],
                reconnect_time_wait=2,
                max_reconnect_attempts=-1
            )
            logger.info(f"Connected to NATS at {settings.NATS_URL}")
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
        Periodically attempts to flush the buffer to NATS.
        """
        while self._running:
            if self.nc.is_connected and self._buffer:
                logger.info(f"Flushing {len(self._buffer)} buffered events...")
                while self._buffer:
                    if not self.nc.is_connected:
                        break # Stop flushing if connection lost
                    
                    event_data = self._buffer[0] # Peek
                    try:
                        subject = f"n7.events.{settings.AGENT_TYPE}.{settings.AGENT_SUBTYPE}"
                        payload = json.dumps(event_data).encode()
                        await self.nc.publish(subject, payload)
                        self._buffer.popleft() # Remove only after successful publish (or at least sent)
                    except Exception as e:
                        logger.error(f"Failed to flush event: {e}")
                        await asyncio.sleep(1) # Backoff on error
                        break
            
            await asyncio.sleep(1) # Check every second

    async def emit(self, event_data: dict):
        """
        Publishes an event to NATS or buffers it.
        """
        if not self.nc.is_connected:
            if self._buffer.maxlen and len(self._buffer) < self._buffer.maxlen:
                self._buffer.append(event_data)
                logger.warning(f"NATS not connected. Buffered event. Buffer size: {len(self._buffer)}")
            elif self._buffer.maxlen is None: # Should not happen with maxlen=1000 but for type safety
                 self._buffer.append(event_data)
            else:
                logger.error("Buffer full! Dropping event.")
            return

        try:
            subject = f"n7.events.{settings.AGENT_TYPE}.{settings.AGENT_SUBTYPE}"
            payload = json.dumps(event_data).encode()
            await self.nc.publish(subject, payload)
        except Exception as e:
            logger.error(f"Failed to emit event: {e}")
            # Try to buffer if publish failed
            if self._buffer.maxlen and len(self._buffer) < self._buffer.maxlen:
                self._buffer.append(event_data)

