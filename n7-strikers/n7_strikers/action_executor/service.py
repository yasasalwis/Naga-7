import asyncio
import logging
import json
from ..service_manager.base_service import BaseService
from ..messaging.nats_client import nats_client
from ..config import settings
from ..actions.kill_process import KillProcessAction
from google.protobuf.json_format import MessageToDict
try:
    from schemas.actions_pb2 import Action as ProtoAction
except ImportError:
    pass

logger = logging.getLogger("n7-striker.action-executor")

class ActionExecutorService(BaseService):
    """
    Action Executor Service.
    Responsibility: Receive actions from Core and execute them.
    """
    def __init__(self):
        super().__init__("ActionExecutorService")
        self._running = False
        self.actions = {
            "kill_process": KillProcessAction()
        }

    async def start(self):
        self._running = True
        logger.info("ActionExecutorService started.")
        
        if nats_client.nc.is_connected:
            subject = f"n7.actions.{settings.AGENT_ID}"
            await nats_client.nc.subscribe(
                subject, 
                cb=self.handle_action
            )
            logger.info(f"Subscribed to {subject}")
            
            # Also subscribe to broadcast/zone actions if needed
        else:
            logger.warning("NATS not connected.")

    async def stop(self):
        self._running = False
        logger.info("ActionExecutorService stopped.")

    async def handle_action(self, msg):
        try:
            proto_action = ProtoAction()
            proto_action.ParseFromString(msg.data)
            
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
            
            # Report status back to Core (TODO: Implement status reporting)
            # await nats_client.nc.publish("n7.actions.status", ...)

        except Exception as e:
            logger.error(f"Error processing action: {e}")
