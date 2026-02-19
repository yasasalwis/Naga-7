import asyncio
import json
import logging
from datetime import datetime, timedelta
from typing import Dict, Optional

logger = logging.getLogger("n7-striker.rollback-manager")


class RollbackManagerService:
    """
    Rollback Manager Service.
    Responsibility: Track active actions that can be reversed, schedule timed rollbacks,
    and execute rollback on demand.
    Ref: TDD Section 6.1 Striker Process Model
    """

    def __init__(self):
        self._running = False
        # In-memory ledger: {action_id: rollback_entry}
        self._rollback_ledger: Dict[str, dict] = {}
        self._scheduler_task: Optional[asyncio.Task] = None

    async def start(self):
        self._running = True
        self._scheduler_task = asyncio.create_task(self._rollback_scheduler_loop())
        logger.info("RollbackManagerService started.")

    async def stop(self):
        self._running = False
        if self._scheduler_task:
            self._scheduler_task.cancel()
            try:
                await self._scheduler_task
            except asyncio.CancelledError:
                pass
        logger.info("RollbackManagerService stopped.")

    def register_rollback(
        self,
        action_id: str,
        action_type: str,
        rollback_action_type: str,
        rollback_params: dict,
        auto_rollback_seconds: Optional[int] = None,
    ):
        """
        Register a rollback entry for a completed action.

        Args:
            action_id: The original action UUID
            action_type: e.g., "isolate_host"
            rollback_action_type: e.g., "unisolate_host"
            rollback_params: params dict for the rollback action
            auto_rollback_seconds: If set, automatically trigger rollback after this many seconds
        """
        entry = {
            "action_id": action_id,
            "action_type": action_type,
            "rollback_action_type": rollback_action_type,
            "rollback_params": rollback_params,
            "registered_at": datetime.utcnow().isoformat(),
            "auto_rollback_at": None,
            "rolled_back": False,
        }
        if auto_rollback_seconds:
            rollback_time = datetime.utcnow() + timedelta(seconds=auto_rollback_seconds)
            entry["auto_rollback_at"] = rollback_time.isoformat()

        self._rollback_ledger[action_id] = entry
        logger.info(
            f"Rollback registered for action {action_id}: {rollback_action_type}"
            + (f" (auto in {auto_rollback_seconds}s)" if auto_rollback_seconds else "")
        )

    async def _rollback_scheduler_loop(self):
        """Check for expired auto-rollbacks every 30 seconds."""
        while self._running:
            now = datetime.utcnow()
            for action_id, entry in list(self._rollback_ledger.items()):
                if entry.get("rolled_back"):
                    continue
                auto_at = entry.get("auto_rollback_at")
                if auto_at:
                    rollback_time = datetime.fromisoformat(auto_at)
                    if now >= rollback_time:
                        logger.info(f"Auto-rollback triggered for action {action_id}")
                        await self._execute_rollback(action_id, entry)
            await asyncio.sleep(30)

    async def _execute_rollback(self, action_id: str, entry: dict):
        """Publish a rollback action to the striker's own NATS subject."""
        try:
            from ..messaging.nats_client import nats_client
            from ..config import settings

            rollback_payload = json.dumps({
                "action_id": f"rollback_{action_id}",
                "action_type": entry["rollback_action_type"],
                "params": entry["rollback_params"],
                "timestamp": datetime.utcnow().isoformat(),
                "is_rollback": True,
                "original_action_id": action_id,
            }).encode()

            if nats_client.nc and nats_client.nc.is_connected:
                await nats_client.nc.publish(
                    f"n7.actions.{settings.AGENT_ID}",
                    rollback_payload
                )
                self._rollback_ledger[action_id]["rolled_back"] = True
                logger.info(f"Rollback action published for original action {action_id}")
            else:
                logger.error(f"NATS not connected, could not publish rollback for {action_id}")
        except Exception as e:
            logger.error(f"Failed to execute rollback for {action_id}: {e}", exc_info=True)
