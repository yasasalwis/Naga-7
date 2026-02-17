import asyncio
import logging
import json
import uuid
from datetime import datetime
from google.protobuf.json_format import MessageToDict
from ..service_manager.base_service import BaseService
from ..messaging.nats_client import nats_client
from ..database.session import async_session_maker
from ..models.alert import Alert as AlertModel
# Protobuf schemas generated successfully
from schemas.alerts_pb2 import Alert as ProtoAlert

logger = logging.getLogger("n7-core.decision-engine")

class DecisionEngineService(BaseService):
    """
    Decision Engine Service.
    Responsibility: Evaluate alerts and produce verdicts.
    """
    def __init__(self):
        super().__init__("DecisionEngineService")
        self._running = False

    async def start(self):
        self._running = True
        logger.info("DecisionEngineService started.")
        
        if nats_client.nc and nats_client.nc.is_connected:
            await nats_client.nc.subscribe(
                "n7.alerts", 
                cb=self.handle_alert,
                queue="decision_engine"
            )
            logger.info("Subscribed to n7.alerts")
        else:
            logger.warning("NATS not connected, DecisionEngineService waiting...")

    async def stop(self):
        self._running = False
        logger.info("DecisionEngineService stopped.")

    async def handle_alert(self, msg):
        try:
            proto_alert = ProtoAlert()
            proto_alert.ParseFromString(msg.data)
            
            logger.info(f"Received alert: {proto_alert.alert_id} severity={proto_alert.severity}")
            
            # Simple Escalation Policy Logic
            severity = proto_alert.severity.lower()
            verdict = "dismiss"
            action_to_take = None
            
            if severity == "critical":
                verdict = "escalate"
                # Notify operators (omitted for MVP)
            elif severity == "high":
                 # Auto-respond if confidence is high (simulated)
                 if proto_alert.threat_score > 70:
                     verdict = "auto_respond"
                     # Logic to select action based on reasoning
                     reasoning = json.loads(proto_alert.reasoning) if proto_alert.reasoning else {}
                     if reasoning.get("rule") == "Brute Force":
                         source_ip = reasoning.get("source_ip")
                         if source_ip:
                             action_to_take = {
                                 "action_type": "network_block",
                                 "target": source_ip,
                                 "duration": 3600
                             }
            elif severity == "medium":
                verdict = "escalate"

            logger.info(f"Verdict for {proto_alert.alert_id}: {verdict}")

            # Persist verdict update (Optional for MVP speed, logic usually updates db_alert)
            
            # Dispatch Action
            if verdict == "auto_respond" and action_to_take:
                action_id = str(uuid.uuid4())
                action_payload = {
                    "action_id": action_id,
                    "alert_id": proto_alert.alert_id,
                    "type": action_to_take["action_type"],
                    "params": action_to_take,
                    "timestamp": datetime.utcnow().isoformat()
                }
                
                # Publish to general actions topic (or specific striker)
                # Strikers filter by capability
                if nats_client.nc:
                    await nats_client.nc.publish(
                        f"n7.actions.{action_to_take['action_type']}", 
                        json.dumps(action_payload).encode()
                    )
                    logger.info(f"Dispatched action {action_id}: {action_to_take['action_type']}")

        except Exception as e:
            logger.error(f"Error processing alert: {e}", exc_info=True)
