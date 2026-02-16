import asyncio
import logging
import json
from ..service_manager.base_service import BaseService
from ..messaging.nats_client import nats_client

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
        
        if nats_client.nc.is_connected:
            await nats_client.nc.subscribe(
                "n7.alerts", 
                cb=self.handle_alert,
                queue="decision_engine"
            )
            logger.info("Subscribed to n7.alerts")

    async def stop(self):
        self._running = False
        logger.info("DecisionEngineService stopped.")

    async def handle_alert(self, msg):
        try:
            data = json.loads(msg.data.decode())
            logger.info(f"Received alert: {data.get('alert_id')}")
            
            # Logic: Check severity
            severity = data.get("severity", "low")
            
            if severity in ["critical", "high"]:
                logger.info(f"Escalating {severity} alert {data.get('alert_id')}")
                # Create Incident (DB)
                # Notify (Notifier Service)
            elif severity == "medium":
                logger.info(f"Auto-responding to {severity} alert {data.get('alert_id')}")
                # Select Playbook
                # Dispatch Action
                
        except Exception as e:
            logger.error(f"Error processing alert: {e}")
