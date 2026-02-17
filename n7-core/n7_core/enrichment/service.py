import logging
from typing import Dict

from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.enrichment")


class EnrichmentService(BaseService):
    """
    Enrichment Service.
    Responsibility: Enrich events with contextual metadata.
    Ref: TDD Section 4.2 Event Pipeline Service (Enrichment), SRS FR-C002
    """

    def __init__(self):
        super().__init__("EnrichmentService")
        self._running = False
        self.threat_intel_service = None  # Will be injected

    async def start(self):
        self._running = True
        logger.info("EnrichmentService started.")

    async def stop(self):
        self._running = False
        logger.info("EnrichmentService stopped.")

    def set_threat_intel_service(self, threat_intel_service):
        """Inject ThreatIntelService dependency."""
        self.threat_intel_service = threat_intel_service

    async def enrich_event(self, event_dict: Dict) -> Dict:
        """
        Enrich event with contextual metadata.
        Returns enrichment dictionary to be merged with event.
        
        Enrichments include:
        - Threat intelligence IOC matching
        - GeoIP resolution (future)
        - Asset inventory lookup (future)
        - Historical context (future)
        """
        enrichments = {}

        try:
            # 1. Threat Intelligence Matching
            if self.threat_intel_service:
                raw_data = event_dict.get("raw_data", {})
                threat_intel_enrichments = await self.threat_intel_service.enrich_with_threat_intel(raw_data)
                enrichments.update(threat_intel_enrichments)

            # 2. GeoIP Resolution (Placeholder - would use MaxMind GeoLite2)
            # if "source_ip" in event_dict.get("raw_data", {}):
            #     enrichments["geo_ip"] = await self._lookup_geoip(event_dict["raw_data"]["source_ip"])

            # 3. Asset Inventory Lookup (Placeholder - would query agents table)
            # sentinel_id = event_dict.get("sentinel_id")
            # enrichments["asset_info"] = await self._lookup_asset(sentinel_id)

            # 4. Historical Context (Placeholder - would query Redis for recent events)
            # enrichments["historical_context"] = await self._get_historical_context(event_dict)

            logger.debug(f"Enriched event with {len(enrichments)} enrichment fields")

        except Exception as e:
            logger.error(f"Error enriching event: {e}", exc_info=True)

        return enrichments
