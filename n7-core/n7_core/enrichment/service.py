
import logging
from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.enrichment")

class EnrichmentService(BaseService):
    """
    Enrichment Service.
    Responsibility: Enrich events with contextual metadata.
    Ref: TDD Section 4.2 Event Pipeline Service (Enrichment)
    """
    def __init__(self):
        super().__init__("EnrichmentService")
        self._running = False

    async def start(self):
        self._running = True
        logger.info("EnrichmentService started.")

    async def stop(self):
        self._running = False
        logger.info("EnrichmentService stopped.")
