
import logging
from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.audit-logger")

class AuditLoggerService(BaseService):
    """
    Audit Logger Service.
    Responsibility: Immutable logging of all events, decisions, and actions.
    Ref: TDD Section 4.1 / 3.5 Audit and Compliance
    """
    def __init__(self):
        super().__init__("AuditLoggerService")
        self._running = False

    async def start(self):
        self._running = True
        logger.info("AuditLoggerService started.")

    async def stop(self):
        self._running = False
        logger.info("AuditLoggerService stopped.")
