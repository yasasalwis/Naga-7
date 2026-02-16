
import logging
from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.notifier")

class NotifierService(BaseService):
    """
    Notifier Service.
    Responsibility: Send notifications to external channels (Slack, Email, PagerDuty).
    Ref: TDD Section 4.1 Core Service Decomposition
    """
    def __init__(self):
        super().__init__("NotifierService")
        self._running = False

    async def start(self):
        self._running = True
        logger.info("NotifierService started.")

    async def stop(self):
        self._running = False
        logger.info("NotifierService stopped.")
