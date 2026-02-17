import logging

import nats

# Import generated protobuf class
try:
    from schemas.events_pb2 import Event as ProtoEvent
except ImportError:
    # Fallback or error if schemas not found (should be fixed by sys.path)
    # Re-raising to fail fast
    raise

logger = logging.getLogger("n7-sentinel.event-emitter")


class EventEmitter:
    """
    Event Emitter.
    Responsibility: Emit events to the message bus in the standardized schema.
    """

    def __init__(self, config):
        self.config = config
        self.nc = None
        self.js = None

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
            logger.warning("NATS not connected, dropping event (TODO: implement local cache)")
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

    async def close(self):
        if self.nc:
            await self.nc.close()
