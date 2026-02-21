import json
import logging

from ..actions.kill_process import KillProcessAction
from ..actions.network_block import NetworkBlockAction, NetworkUnblockAction
from ..actions.network_isolator import NetworkIsolatorAction, NetworkUnisolatorAction
from ..agent_id import get_agent_id
from ..agent_runtime.config import settings
from ..evidence_collector.service import EvidenceCollectorService
from ..messaging.nats_client import nats_client
from ..rollback_manager.service import RollbackManagerService

try:
    from schemas.actions_pb2 import Action as ProtoAction
except ImportError:
    ProtoAction = None

logger = logging.getLogger("n7-striker.action-executor")

# Maps action_type -> (rollback_action_type, auto_rollback_seconds)
# None means no auto-rollback (manual only or irreversible)
_ROLLBACK_MAP = {
    "isolate_host": ("unisolate_host", None),   # never auto-undo isolation — requires operator review
    "network_block": ("network_unblock", 3600),  # auto-unblock after 1 hour
}


class _ActionDict:
    """Duck-typed wrapper for JSON-sourced action payloads (no Protobuf)."""
    def __init__(self, data: dict):
        self.action_id = data.get("action_id", "")
        self.incident_id = data.get("incident_id", "")
        self.striker_id = data.get("striker_id", get_agent_id())
        self.action_type = data.get("action_type", data.get("type", ""))
        self.parameters = data.get("parameters", json.dumps(data.get("params", {})))
        self.status = data.get("status", "queued")
        self.result_data = data.get("result_data", "")


class ActionExecutorService:
    """
    Action Executor Service.
    Responsibility: Receive actions from Core, collect pre/post forensic evidence,
    execute the action, register rollback entries, and report full status + evidence
    back to Core via n7.actions.status.
    """

    def __init__(
        self,
        rollback_manager: RollbackManagerService,
        evidence_collector: EvidenceCollectorService,
    ):
        self._running = False
        self._rollback_manager = rollback_manager
        self._evidence_collector = evidence_collector
        self.actions = {
            "kill_process": KillProcessAction(),
            "network_block": NetworkBlockAction(),
            "network_unblock": NetworkUnblockAction(),
            "isolate_host": NetworkIsolatorAction(),
            "unisolate_host": NetworkUnisolatorAction(),
        }

    async def start(self):
        self._running = True
        logger.info("ActionExecutorService started.")

        if nats_client.nc.is_connected:
            subject = f"n7.actions.{get_agent_id()}"
            await nats_client.nc.subscribe(subject, cb=self.handle_action)
            logger.info(f"Subscribed to {subject}")

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
        proto_action = None
        try:
            # Parse: try Protobuf first, fall back to JSON
            if ProtoAction is not None:
                try:
                    _pa = ProtoAction()
                    _pa.ParseFromString(msg.data)
                    if _pa.action_type:
                        proto_action = _pa
                except Exception:
                    proto_action = None

            if proto_action is None:
                data = json.loads(msg.data.decode())
                proto_action = _ActionDict(data)

            action_id = proto_action.action_id
            action_type = proto_action.action_type
            logger.info(f"Received action: {action_id} type={action_type}")

            action_handler = self.actions.get(action_type)
            if not action_handler:
                logger.error(f"Unknown action type: {action_type}")
                return

            # Check against allowed_actions (config-driven allowlist)
            allowed = settings.ALLOWED_ACTIONS
            if allowed is not None and action_type not in allowed:
                logger.warning(
                    f"Action '{action_type}' rejected: not in allowed_actions={allowed}. "
                    "Update striker config to permit this action."
                )
                if nats_client.nc.is_connected:
                    await nats_client.nc.publish("n7.actions.status", json.dumps({
                        "action_id": action_id,
                        "striker_id": get_agent_id(),
                        "action_type": action_type,
                        "status": "rejected",
                        "result_data": {"error": f"Action '{action_type}' not in allowed_actions for this striker."},
                    }).encode())
                return

            try:
                params = json.loads(proto_action.parameters)
            except Exception:
                params = {}

            # Merge action_defaults under params (params from command take precedence)
            defaults = settings.ACTION_DEFAULTS.get(action_type, {})
            params = {**defaults, **params}

            # --- Pre-action forensic evidence ---
            pre_evidence = await self._evidence_collector.collect_pre_action(
                action_id=action_id,
                action_type=action_type,
                params=params,
            )

            # --- Execute action ---
            result = await action_handler.execute(params)
            logger.info(f"Action result: {result}")

            # --- Post-action forensic evidence ---
            post_evidence = await self._evidence_collector.collect_post_action(
                action_id=action_id,
                action_type=action_type,
                result=result,
            )

            # --- Register rollback for reversible actions ---
            if action_type in _ROLLBACK_MAP:
                rollback_type, auto_seconds = _ROLLBACK_MAP[action_type]
                rollback_params = dict(params)
                rollback_params["original_action_id"] = action_id
                self._rollback_manager.register_rollback(
                    action_id=action_id,
                    action_type=action_type,
                    rollback_action_type=rollback_type,
                    rollback_params=rollback_params,
                    auto_rollback_seconds=auto_seconds,
                )

            # --- Report status + evidence to Core ---
            succeeded = result.get("success", result.get("status") == "succeeded")
            status_str = "completed" if succeeded else "failed"
            combined_evidence = {"pre": pre_evidence, "post": post_evidence}

            if nats_client.nc.is_connected:
                if ProtoAction is not None and not isinstance(proto_action, _ActionDict):
                    status_update = ProtoAction()
                    status_update.action_id = action_id
                    status_update.incident_id = proto_action.incident_id
                    status_update.striker_id = get_agent_id()
                    status_update.action_type = action_type
                    status_update.status = status_str
                    status_update.result_data = json.dumps({
                        "result": result,
                        "evidence": combined_evidence,
                    })
                    await nats_client.nc.publish("n7.actions.status", status_update.SerializeToString())
                else:
                    status_payload = json.dumps({
                        "action_id": action_id,
                        "striker_id": get_agent_id(),
                        "action_type": action_type,
                        "status": status_str,
                        "result_data": result,
                        "evidence": combined_evidence,
                    }).encode()
                    await nats_client.nc.publish("n7.actions.status", status_payload)

                logger.info(f"Reported status '{status_str}' for action {action_id}")
            else:
                logger.warning("NATS not connected — could not report action status.")

        except Exception as e:
            logger.error(f"Error processing action: {e}", exc_info=True)
            try:
                if proto_action is not None and nats_client.nc.is_connected:
                    error_payload = json.dumps({
                        "action_id": getattr(proto_action, "action_id", "unknown"),
                        "status": "error",
                        "result_data": {"error": str(e)},
                    }).encode()
                    await nats_client.nc.publish("n7.actions.status", error_payload)
            except Exception:
                pass
