import json
import logging
from datetime import datetime
from typing import Optional, Dict

from ..database.redis import redis_client
from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.threat-intel")


class ThreatIntelService(BaseService):
    """
    Threat Intel Service.
    Responsibility: Manage threat intelligence feeds and IOC matching.
    Ref: TDD Section 4.1 Core Service Decomposition, SRS Section 8.1
    """

    def __init__(self):
        super().__init__("ThreatIntelService")
        self._running = False
        self.ioc_cache_ttl = 3600  # 1 hour default TTL for IOCs

    async def start(self):
        self._running = True
        logger.info("ThreatIntelService started.")
        # Future: Start background task for STIX/TAXII feed ingestion
        # asyncio.create_task(self._feed_ingestion_loop())

    async def stop(self):
        self._running = False
        logger.info("ThreatIntelService stopped.")

    async def check_ioc(self, ioc_type: str, ioc_value: str) -> Optional[Dict]:
        """
        Check if an IOC (Indicator of Compromise) is known malicious.
        Returns IOC details if found, None otherwise.
        
        Args:
            ioc_type: Type of IOC (ip, domain, hash, url)
            ioc_value: The IOC value to check
        
        Returns:
            Dict with IOC details if malicious, None if not found
        """
        try:
            key = f"n7:ioc:{ioc_type}:{ioc_value}"
            cached = await redis_client.get(key)

            if cached:
                logger.debug(f"IOC cache hit: {ioc_type}={ioc_value}")
                return json.loads(cached)

            # Future: Query database for IOCs if not in cache
            # For now, return None (not found)
            return None

        except Exception as e:
            logger.error(f"Error checking IOC: {e}", exc_info=True)
            return None

    async def add_ioc(self, ioc_type: str, ioc_value: str, confidence: float, source: str, metadata: Dict = None):
        """
        Add an IOC to the threat intelligence cache.
        
        Args:
            ioc_type: Type of IOC (ip, domain, hash, url)
            ioc_value: The IOC value
            confidence: Confidence score 0.0-1.0
            source: Source of the intel (e.g., "manual", "feed:abuse.ch")
            metadata: Additional metadata about the IOC
        """
        try:
            ioc_data = {
                "ioc_type": ioc_type,
                "ioc_value": ioc_value,
                "confidence": confidence,
                "source": source,
                "metadata": metadata or {},
                "added_at": datetime.utcnow().isoformat()
            }

            key = f"n7:ioc:{ioc_type}:{ioc_value}"
            await redis_client.set(key, json.dumps(ioc_data), ex=self.ioc_cache_ttl)

            logger.info(f"Added IOC: {ioc_type}={ioc_value} from {source}")

        except Exception as e:
            logger.error(f"Error adding IOC: {e}", exc_info=True)

    async def enrich_with_threat_intel(self, event_data: Dict) -> Dict:
        """
        Enrich event data with threat intelligence matches.
        Checks common IOC fields and returns enrichments.
        
        Returns:
            Dict with threat_intel field containing matches
        """
        enrichments = {"threat_intel_matches": []}

        try:
            # Check common IOC fields
            checks = []

            if "source_ip" in event_data:
                checks.append(("ip", event_data["source_ip"]))
            if "destination_ip" in event_data:
                checks.append(("ip", event_data["destination_ip"]))
            if "domain" in event_data:
                checks.append(("domain", event_data["domain"]))
            if "file_hash" in event_data:
                checks.append(("hash", event_data["file_hash"]))
            if "url" in event_data:
                checks.append(("url", event_data["url"]))

            for ioc_type, ioc_value in checks:
                match = await self.check_ioc(ioc_type, ioc_value)
                if match:
                    enrichments["threat_intel_matches"].append(match)
                    logger.info(f"Threat intel match: {ioc_type}={ioc_value}")

        except Exception as e:
            logger.error(f"Error enriching with threat intel: {e}", exc_info=True)

        return enrichments
