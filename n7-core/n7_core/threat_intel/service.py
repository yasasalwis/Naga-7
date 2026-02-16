
import logging
from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.threat-intel")

class ThreatIntelService(BaseService):
    """
    Threat Intel Service.
    Responsibility: Manage threat intelligence feeds and IOC matching.
    Ref: TDD Section 4.1 Core Service Decomposition
    """
    def __init__(self):
        super().__init__("ThreatIntelService")
        self._running = False

    async def start(self):
        self._running = True
        logger.info("ThreatIntelService started.")

    async def stop(self):
        self._running = False
        logger.info("ThreatIntelService stopped.")
