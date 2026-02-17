import json
import logging
import uuid
from datetime import datetime

# Protobuf schemas generated successfully
from schemas.alerts_pb2 import Alert as ProtoAlert
from schemas.events_pb2 import Event as ProtoEvent

from ..database.redis import redis_client
from ..database.session import async_session_maker
from ..messaging.nats_client import nats_client
from ..models.alert import Alert as AlertModel
from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.threat-correlator")

class ThreatCorrelatorService(BaseService):
    """
    Threat Correlator Service.
    Responsibility: Correlate individual events/alerts into multi-stage attack patterns.
    """
    def __init__(self):
        super().__init__("ThreatCorrelatorService")
        self._running = False
        # Simple rule config
        self.brute_force_threshold = 5
        self.brute_force_window = 60 # seconds

    async def start(self):
        self._running = True
        logger.info("ThreatCorrelatorService started.")
        
        # Subscribe to internal processed events
        if nats_client.nc and nats_client.nc.is_connected:
             await nats_client.nc.subscribe(
                 "n7.internal.events", 
                 cb=self.handle_internal_event,
                 queue="threat_correlator"
             )
             logger.info("Subscribed to n7.internal.events")
        else:
            logger.warning("NATS not connected, ThreatCorrelatorService waiting...")

    async def stop(self):
        self._running = False
        logger.info("ThreatCorrelatorService stopped.")

    async def handle_internal_event(self, msg):
        try:
            proto_event = ProtoEvent()
            proto_event.ParseFromString(msg.data)
            
            # Simple Correlation Rule: Detect High Frequency "authentication_failure" from same IP
            # We need to extract source IP from raw_data.
            # Assuming raw_data is a JSON string or dict in proto (it is string in proto definition usually, let's check)
            # In `events.proto`, raw_data is bytes or string? Actually `events.proto` isn't fully visible but `service.py` treated it as field.
            # Let's assume raw_data is a JSON string.
            
            raw_data = json.loads(proto_event.raw_data) if isinstance(proto_event.raw_data, str) else proto_event.raw_data
            if isinstance(raw_data, bytes):
                 raw_data = json.loads(raw_data.decode())

            event_class = proto_event.event_class
            
            # Rule 1: Brute Force Detection
            if event_class == "authentication" and raw_data.get("outcome") == "failure":
                source_ip = raw_data.get("source_ip")
                if source_ip:
                    await self._check_brute_force(source_ip, proto_event.event_id)

        except Exception as e:
            logger.error(f"Error in ThreatCorrelator: {e}", exc_info=True)

    async def _check_brute_force(self, source_ip: str, event_id: str):
        key = f"n7:corr:brute:{source_ip}"
        
        # Increment counter
        count = await redis_client.incr(key)
        
        # Set expiry on first increment
        if count == 1:
            await redis_client.expire(key, self.brute_force_window)
        
        if count >= self.brute_force_threshold:
            # Trigger Alert
            logger.warning(f"Brute force detected from {source_ip} (count={count})")
            
            # Create Alert
            alert_id = str(uuid.uuid4())
            alert = ProtoAlert(
                alert_id=alert_id,
                created_at=datetime.utcnow().isoformat(),
                event_ids=[event_id], # Ideally we collect all related event IDs from Redis/DB
                threat_score=75,
                severity="high",
                status="new",
                verdict="pending",
                reasoning=json.dumps({"rule": "Brute Force", "count": count, "source_ip": source_ip}),
                affected_assets=[source_ip]
            )
            
            # Persist Alert
            async with async_session_maker() as session:
                db_alert = AlertModel(
                    alert_id=uuid.UUID(alert_id),
                    created_at=datetime.utcnow(),
                    event_ids=[event_id],
                    threat_score=75,
                    severity="high",
                    status="new",
                    verdict="pending",
                    affected_assets=[source_ip],
                    reasoning={"rule": "Brute Force", "count": count, "source_ip": source_ip}
                )
                session.add(db_alert)
                await session.commit()

            # Publish Alert
            if nats_client.nc:
                await nats_client.nc.publish("n7.alerts", alert.SerializeToString())
            
            # Reset counter after alert to avoid spamming (or implement separate cooldown)
            await redis_client.delete(key)
