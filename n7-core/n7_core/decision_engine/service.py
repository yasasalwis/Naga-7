import json
import logging
import uuid
from datetime import datetime

# Protobuf schemas generated successfully
from schemas.alerts_pb2 import Alert as ProtoAlert
from ..database.session import async_session_maker
from ..messaging.nats_client import nats_client
from ..models.action import Action as ActionModel
from ..service_manager.base_service import BaseService

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

            await nats_client.nc.subscribe(
                "n7.actions.status",
                cb=self.handle_action_status,
                queue="decision_engine_action_status"
            )
            logger.info("Subscribed to n7.actions.status")
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
                reasoning = json.loads(proto_alert.reasoning) if proto_alert.reasoning else {}
                # Auto-isolate host for multi-stage critical attacks
                if reasoning.get("is_multi_stage") and reasoning.get("source"):
                    verdict = "auto_respond"
                    action_to_take = {
                        "action_type": "isolate_host",
                        "reason": reasoning.get("rule", "multi_stage_critical_attack"),
                        "alert_id": proto_alert.alert_id,
                        "source": reasoning.get("source"),
                    }
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

                # Publish to broadcast subject so any capable striker handles it
                if nats_client.nc:
                    await nats_client.nc.publish(
                        "n7.actions.broadcast",
                        json.dumps(action_payload).encode()
                    )
                    logger.info(f"Dispatched action {action_id}: {action_to_take['action_type']} via broadcast")

        except Exception as e:
            logger.error(f"Error processing alert: {e}", exc_info=True)

    async def handle_action_status(self, msg):
        """
        Receive action completion reports from Strikers on n7.actions.status.
        Persists the final status, result, and forensic evidence into the actions table.
        """
        try:
            # Try JSON (primary format); Protobuf actions have result_data as a JSON string
            try:
                data = json.loads(msg.data.decode())
            except Exception:
                # Fallback: Protobuf serialized — try to parse action_id and status from ProtoAction
                try:
                    from schemas.actions_pb2 import Action as ProtoAction
                    pa = ProtoAction()
                    pa.ParseFromString(msg.data)
                    result_raw = pa.result_data or "{}"
                    inner = json.loads(result_raw)
                    data = {
                        "action_id": pa.action_id,
                        "striker_id": pa.striker_id,
                        "action_type": pa.action_type,
                        "status": pa.status,
                        "result_data": inner.get("result", {}),
                        "evidence": inner.get("evidence", {}),
                    }
                except Exception:
                    logger.error("handle_action_status: could not decode message", exc_info=True)
                    return

            action_id_str = data.get("action_id")
            if not action_id_str:
                logger.warning("handle_action_status: missing action_id in payload")
                return

            status = data.get("status", "unknown")
            result_data = data.get("result_data", {})
            evidence = data.get("evidence", {})

            logger.info(f"Action status received: {action_id_str} → {status}")

            async with async_session_maker() as session:
                from sqlalchemy import select
                result = await session.execute(
                    select(ActionModel).where(
                        ActionModel.action_id == uuid.UUID(action_id_str)
                    )
                )
                action = result.scalar_one_or_none()

                if action is None:
                    # Action was dispatched without a prior DB row (decision engine auto-dispatch).
                    # Create a record now from the status report.
                    action = ActionModel(
                        action_id=uuid.UUID(action_id_str),
                        action_type=data.get("action_type", "unknown"),
                        status=status,
                        initiated_by="auto",
                        parameters={},
                        evidence=evidence,
                        rollback_entry={},
                    )
                    session.add(action)
                    logger.info(f"Created action record from status report for {action_id_str}")
                else:
                    action.status = status
                    if evidence:
                        action.evidence = evidence
                    if result_data:
                        # Merge result data into rollback_entry field (already a JSON blob)
                        action.rollback_entry = {
                            **(action.rollback_entry or {}),
                            "execution_result": result_data,
                        }

                await session.commit()
                logger.debug(f"Persisted action status for {action_id_str}: {status}")

        except Exception as e:
            logger.error(f"Error processing action status: {e}", exc_info=True)
