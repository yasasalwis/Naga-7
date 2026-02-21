import asyncio
import json
import logging
import pathlib

import nats

# Import generated protobuf class
try:
    from schemas.events_pb2 import Event as ProtoEvent
except ImportError:
    # Fallback or error if schemas not found (should be fixed by sys.path)
    # Re-raising to fail fast
    raise

logger = logging.getLogger("n7-sentinel.event-emitter")

_LOCAL_CACHE_PATH = pathlib.Path("/tmp/n7_event_cache.jsonl")


class EventEmitter:
    """
    Event Emitter.
    Responsibility: Emit events to the message bus in the standardized schema.
    Falls back to a local JSON-line file cache when JetStream is unavailable,
    and replays cached events automatically on reconnect.
    """

    def __init__(self, config):
        self.config = config
        self.nc = None
        self.js = None
        self._local_cache_path = _LOCAL_CACHE_PATH
        self._reconnect_task: asyncio.Task | None = None

    async def connect(self):
        try:
            self.nc = await nats.connect(self.config.NATS_URL)
            self.js = self.nc.jetstream()
            # Ensure stream exists? Core might handle this, or idempotent creation.
            # strict adherence to TDD: Core lifecycle manages things, but Sentinel should be robust.
            logger.info(f"Connected to NATS at {self.config.NATS_URL}")
        except Exception as e:
            logger.error(f"Failed to connect to NATS: {e}")

    async def emit(self, event_data: dict):
        if not self.js:
            await self._cache_locally(event_data)
            if self._reconnect_task is None or self._reconnect_task.done():
                self._reconnect_task = asyncio.create_task(self._reconnect_and_flush())
            return

        try:
            # Create Protobuf Event
            proto_event = ProtoEvent(
                event_id=event_data.get("event_id"),
                timestamp=event_data.get("timestamp"),
                sentinel_id=event_data.get("sentinel_id"),
                event_class=event_data.get("event_class"),
                severity=event_data.get("severity", "info"),
                raw_data=event_data.get("raw_data", "{}")  # JSON string
            )

            # Serialize
            payload = proto_event.SerializeToString()

            # Publish
            subject = f"n7.events.{self.config.AGENT_SUBTYPE}"
            await self.js.publish(subject, payload)
            logger.debug(f"Emitted event {proto_event.event_id} to {subject}")

        except Exception as e:
            logger.error(f"Failed to emit event: {e}")
            await self._cache_locally(event_data)

    async def _cache_locally(self, event_data: dict):
        """Write event to local JSON-line file for later replay."""
        try:
            line = json.dumps(event_data) + "\n"
            await asyncio.to_thread(
                lambda: self._local_cache_path.open("a").write(line)
            )
            logger.warning(f"NATS not connected. Cached event to {self._local_cache_path}")
        except Exception as e:
            logger.error(f"Failed to write event to local cache: {e}")

    async def _reconnect_and_flush(self):
        """
        Retry connecting to NATS every 5 seconds.
        Once connected, replay all cached events from the local file.
        """
        while not self.js:
            await asyncio.sleep(5)
            try:
                await self.connect()
            except Exception:
                continue

        # JetStream restored — flush cached events
        if not self._local_cache_path.exists():
            return
        try:
            lines = self._local_cache_path.read_text().splitlines()
            self._local_cache_path.unlink()
            logger.info(f"Flushing {len(lines)} cached events after NATS reconnect...")
            for line in lines:
                try:
                    event_data = json.loads(line)
                    await self.emit(event_data)
                except Exception as parse_err:
                    logger.error(f"Failed to replay cached event: {parse_err}")
        except Exception as e:
            logger.error(f"Failed to flush local event cache: {e}")

    async def close(self):
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass
        if self.nc:
            await self.nc.close()
