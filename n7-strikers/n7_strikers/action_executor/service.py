import json
import logging

from ..actions.kill_process import KillProcessAction
from ..actions.network_isolator import NetworkIsolatorAction, NetworkUnisolatorAction
from ..config import settings
from ..messaging.nats_client import nats_client

try:
    from schemas.actions_pb2 import Action as ProtoAction
except ImportError:
    ProtoAction = None

logger = logging.getLogger("n7-striker.action-executor")


class _ActionDict:
    """Duck-typed wrapper for JSON-sourced action payloads (no Protobuf)."""
    def __init__(self, data: dict):
        self.action_id = data.get("action_id", "")
        self.incident_id = data.get("incident_id", "")
        self.striker_id = data.get("striker_id", settings.AGENT_ID)
        self.action_type = data.get("action_type", data.get("type", ""))
        self.parameters = data.get("parameters", json.dumps(data.get("params", {})))
        self.status = data.get("status", "queued")
        self.result_data = data.get("result_data", "")


class ActionExecutorService:
    """
    Action Executor Service.
    Responsibility: Receive actions from Core and execute them.
    """

    def __init__(self):
        self._running = False
        self.actions = {
            "kill_process": KillProcessAction(),
            "isolate_host": NetworkIsolatorAction(),
            "unisolate_host": NetworkUnisolatorAction(),
        }

    async def start(self):
        self._running = True
        logger.info("ActionExecutorService started.")

        if nats_client.nc.is_connected:
            # Subscribe to agent-specific action subject
            subject = f"n7.actions.{settings.AGENT_ID}"
            await nats_client.nc.subscribe(
                subject,
                cb=self.handle_action
            )
            logger.info(f"Subscribed to {subject}")

            # Subscribe to broadcast subject (for Core dispatching without a specific agent ID)
            await nats_client.nc.subscribe(
                "n7.actions.broadcast",
                cb=self.handle_action,
                queue="action_executor"
            )
            logger.info("Subscribed to n7.actions.broadcast")
        else:
            logger.warning("NATS not connected.")

    async def stop(self):
        self._running = False
        logger.info("ActionExecutorService stopped.")

    async def handle_action(self, msg):
        try:
            # Try Protobuf first; fall back to JSON for actions dispatched as plain JSON
            proto_action = None
            if ProtoAction is not None:
                try:
                    _pa = ProtoAction()
                    _pa.ParseFromString(msg.data)
                    # Basic sanity check: Protobuf decode can silently succeed on JSON bytes
                    if _pa.action_type:
                        proto_action = _pa
                except Exception:
                    proto_action = None

            if proto_action is None:
                data = json.loads(msg.data.decode())
                proto_action = _ActionDict(data)

            logger.info(f"Received action: {proto_action.action_id} type={proto_action.action_type}")

            action_handler = self.actions.get(proto_action.action_type)
            if not action_handler:
                logger.error(f"Unknown action type: {proto_action.action_type}")
                return

            # Parse parameters
            try:
                params = json.loads(proto_action.parameters)
            except:
                params = {}

            # Execute
            result = await action_handler.execute(params)
            logger.info(f"Action execution result: {result}")

            # Report status back to Core
            if nats_client.nc.is_connected:
                if ProtoAction is not None and not isinstance(proto_action, _ActionDict):
                    status_update = ProtoAction()
                    status_update.action_id = proto_action.action_id
                    status_update.incident_id = proto_action.incident_id
                    status_update.striker_id = settings.AGENT_ID
                    status_update.action_type = proto_action.action_type
                    status_update.status = "completed" if result.get("success", False) else "failed"
                    status_update.result_data = json.dumps(result)
                    await nats_client.nc.publish("n7.actions.status", status_update.SerializeToString())
                else:
                    status_payload = json.dumps({
                        "action_id": proto_action.action_id,
                        "striker_id": settings.AGENT_ID,
                        "action_type": proto_action.action_type,
                        "status": "completed" if result.get("success", False) else "failed",
                        "result_data": result,
                    }).encode()
                    await nats_client.nc.publish("n7.actions.status", status_payload)
                logger.info(f"Reported status for action {proto_action.action_id}")
            else:
                logger.warning("NATS not connected. Could not report status.")

        except Exception as e:
            logger.error(f"Error processing action: {e}")
            try:
                if 'proto_action' in locals() and nats_client.nc.is_connected:
                    error_payload = json.dumps({
                        "action_id": getattr(proto_action, "action_id", "unknown"),
                        "status": "error",
                        "result_data": {"error": str(e)},
                    }).encode()
                    await nats_client.nc.publish("n7.actions.status", error_payload)
            except Exception:
                pass
