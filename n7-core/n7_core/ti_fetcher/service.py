import asyncio
import logging
import os
import re
from typing import Optional

import httpx

from ..service_manager.base_service import BaseService
from ..threat_intel.service import ThreatIntelService

logger = logging.getLogger("n7-core.ti-fetcher")

# Feed definitions — each entry is a dict describing the feed and its parser method
TI_FEEDS = [
    {
        "name": "OTX AlienVault",
        "url": "https://otx.alienvault.com/api/v1/pulses/subscribed?limit=20",
        "parser": "_parse_otx",
        "requires_auth": True,
        "auth_header": "X-OTX-API-KEY",
        "auth_env": "OTX_API_KEY",
    },
    {
        "name": "Abuse.ch URLhaus",
        "url": "https://urlhaus-api.abuse.ch/v1/urls/recent/limit/500/",
        "parser": "_parse_urlhaus",
        "requires_auth": False,
    },
    {
        "name": "Feodo Tracker",
        "url": "https://feodotracker.abuse.ch/downloads/ipblocklist.json",
        "parser": "_parse_feodo",
        "requires_auth": False,
    },
]

_IP_PATTERN = re.compile(r"^\d{1,3}(\.\d{1,3}){3}$")
IOC_TTL = 86400  # 24-hour TTL for feed-sourced IOCs


class TIFetcherService(BaseService):
    """
    Threat Intelligence Fetcher Service.
    Responsibility: Periodically download IOC lists from open-source TI feeds
    (OTX AlienVault, Abuse.ch URLhaus, Feodo Tracker) and populate the Redis
    IOC cache via ThreatIntelService.

    Ref: TDD Section 4.X TI Fetcher, SRS FR-C011
    """

    def __init__(self, threat_intel_service: ThreatIntelService):
        super().__init__("TIFetcherService")
        self._running = False
        self._threat_intel = threat_intel_service
        self._http_client: Optional[httpx.AsyncClient] = None
        self._fetch_interval: int = int(os.environ.get("TI_FETCH_INTERVAL", "3600"))
        self._fetch_task: Optional[asyncio.Task] = None

    async def start(self):
        self._running = True
        self._http_client = httpx.AsyncClient(
            timeout=30.0,
            follow_redirects=True,
            headers={"User-Agent": "N7-TIFetcher/1.0"},
        )
        logger.info(f"TIFetcherService started. Fetch interval: {self._fetch_interval}s")
        # Kick off immediately then loop
        self._fetch_task = asyncio.create_task(self._feed_ingestion_loop())

    async def stop(self):
        self._running = False
        if self._fetch_task:
            self._fetch_task.cancel()
            try:
                await self._fetch_task
            except asyncio.CancelledError:
                pass
        if self._http_client:
            await self._http_client.aclose()
        logger.info("TIFetcherService stopped.")

    # ------------------------------------------------------------------
    # Feed ingestion loop
    # ------------------------------------------------------------------

    async def _feed_ingestion_loop(self):
        while self._running:
            try:
                await self._fetch_all_feeds()
            except Exception as e:
                logger.error(f"Error during TI feed fetch cycle: {e}", exc_info=True)
            await asyncio.sleep(self._fetch_interval)

    async def _fetch_all_feeds(self):
        logger.info("Starting TI feed ingestion cycle...")
        total = 0
        for feed in TI_FEEDS:
            try:
                count = await self._fetch_feed(feed)
                total += count
            except Exception as e:
                logger.warning(f"Feed '{feed['name']}' failed: {e}")
        logger.info(f"TI feed ingestion cycle complete. Total IOCs ingested: {total}")

    async def _fetch_feed(self, feed: dict) -> int:
        """Download a single feed and dispatch to the appropriate parser."""
        headers = {}
        if feed.get("requires_auth"):
            api_key = os.environ.get(feed["auth_env"], "")
            if not api_key:
                logger.warning(
                    f"Feed '{feed['name']}' requires auth but {feed['auth_env']} env var not set. Skipping."
                )
                return 0
            headers[feed["auth_header"]] = api_key

        response = await self._http_client.get(feed["url"], headers=headers)
        response.raise_for_status()

        parser = getattr(self, feed["parser"])
        count = await parser(response)
        logger.info(f"Feed '{feed['name']}': ingested {count} IOCs.")
        return count

    # ------------------------------------------------------------------
    # Feed parsers
    # ------------------------------------------------------------------

    async def _parse_otx(self, response: httpx.Response) -> int:
        """
        Parse OTX AlienVault subscribed pulses response.
        Extracts IPv4, domain, URL, and file hash indicators.
        """
        count = 0
        data = response.json()
        ioc_type_map = {
            "IPv4": "ip",
            "domain": "domain",
            "URL": "url",
            "hostname": "domain",
            "FileHash-MD5": "hash",
            "FileHash-SHA1": "hash",
            "FileHash-SHA256": "hash",
        }
        for pulse in data.get("results", []):
            pulse_name = pulse.get("name", "OTX")
            pulse_id = pulse.get("id", "")
            for indicator in pulse.get("indicators", []):
                raw_type = indicator.get("type", "")
                mapped_type = ioc_type_map.get(raw_type)
                if not mapped_type:
                    continue
                ioc_value = indicator.get("indicator", "").strip()
                if not ioc_value:
                    continue
                await self._threat_intel.add_ioc(
                    ioc_type=mapped_type,
                    ioc_value=ioc_value,
                    confidence=0.85,
                    source=f"feed:otx:{pulse_name}",
                    metadata={"pulse_id": pulse_id, "raw_type": raw_type},
                    ttl=IOC_TTL,
                )
                count += 1
        return count

    async def _parse_urlhaus(self, response: httpx.Response) -> int:
        """
        Parse Abuse.ch URLhaus recent URLs JSON response.
        Extracts malicious URLs and associated IPs/domains.
        """
        count = 0
        data = response.json()
        for entry in data.get("urls", []):
            threat_type = entry.get("threat", "")
            date_added = entry.get("date_added", "")
            tags = entry.get("tags") or []

            # URL IOC
            url_value = (entry.get("url") or "").strip()
            if url_value:
                await self._threat_intel.add_ioc(
                    ioc_type="url",
                    ioc_value=url_value,
                    confidence=0.90,
                    source="feed:urlhaus",
                    metadata={"threat_type": threat_type, "tags": tags, "date_added": date_added},
                    ttl=IOC_TTL,
                )
                count += 1

            # Host IOC (may be IP or domain)
            host = (entry.get("host") or "").strip()
            if host:
                ioc_type = "ip" if _IP_PATTERN.match(host) else "domain"
                await self._threat_intel.add_ioc(
                    ioc_type=ioc_type,
                    ioc_value=host,
                    confidence=0.80,
                    source="feed:urlhaus",
                    metadata={"threat_type": threat_type},
                    ttl=IOC_TTL,
                )
                count += 1
        return count

    async def _parse_feodo(self, response: httpx.Response) -> int:
        """
        Parse Feodo Tracker IP blocklist JSON.
        Each entry is a botnet C2 server IP.
        """
        count = 0
        data = response.json()
        for entry in data:
            ip = (entry.get("ip_address") or "").strip()
            if not ip:
                continue
            await self._threat_intel.add_ioc(
                ioc_type="ip",
                ioc_value=ip,
                confidence=0.95,
                source="feed:feodo",
                metadata={
                    "malware": entry.get("malware", ""),
                    "status": entry.get("status", ""),
                    "first_seen": entry.get("first_seen", ""),
                    "last_online": entry.get("last_online", ""),
                },
                ttl=IOC_TTL,
            )
            count += 1
        return count
