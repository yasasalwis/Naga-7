
import logging

logger = logging.getLogger("n7-striker.evidence-collector")

class EvidenceCollectorService:
    """
    Evidence Collector Service.
    Responsibility: Forensically capture state before/after actions.
    Ref: TDD Section 6.1 Striker Process Model
    """
    def __init__(self):
        self._running = False

    async def start(self):
        self._running = True
        logger.info("EvidenceCollectorService started.")

    async def stop(self):
        self._running = False
        logger.info("EvidenceCollectorService stopped.")
