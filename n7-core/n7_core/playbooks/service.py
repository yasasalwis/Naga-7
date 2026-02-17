import logging

from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.playbook-engine")


class PlaybookEngineService(BaseService):
    """
    Playbook Engine Service.
    Responsibility: Manage and execute playbooks.
    Ref: TDD Section 6.3 Playbook Engine
    """

    def __init__(self):
        super().__init__("PlaybookEngineService")
        self._running = False

    async def start(self):
        self._running = True
        logger.info("PlaybookEngineService started.")

    async def stop(self):
        self._running = False
        logger.info("PlaybookEngineService stopped.")
