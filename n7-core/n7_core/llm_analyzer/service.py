import json
import logging
import uuid
from datetime import datetime
from typing import Optional

import httpx

from ..database.redis import redis_client
from ..database.session import async_session_maker
from ..messaging.nats_client import nats_client
from ..models.alert import Alert as AlertModel
from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.llm-analyzer")

# System prompt sent to Ollama before each alert bundle
_SYSTEM_PROMPT = (
    "You are a senior cybersecurity analyst AI assistant. "
    "Analyze the security alert bundle provided and return ONLY a JSON object "
    "(no markdown, no explanation outside the JSON) with exactly three keys:\n"
    "  \"narrative\": a concise 2-4 sentence plain-English description of the attack,\n"
    "  \"mitre_tactic\": the most relevant MITRE ATT&CK tactic name (e.g. 'Lateral Movement'),\n"
    "  \"mitre_technique\": the most relevant technique ID and name "
    "(e.g. 'T1021 - Remote Services').\n"
    "Focus on what the attacker likely did, why it is dangerous, and what MITRE stage it represents."
)


class LLMAnalyzerService(BaseService):
    """
    LLM Analyzer Service.
    Responsibility: Subscribe to n7.llm.analyze, call a local Ollama LLM to generate
    a plain-English attack narrative + MITRE ATT&CK mapping for each alert, persist the
    enrichment to the database, then republish the enriched alert to n7.alerts for the
    Decision Engine.

    Gracefully degrades to a structured fallback narrative if Ollama is unavailable.
    Ref: TDD Section 4.X LLM Analyzer, SRS FR-C010
    """

    def __init__(self):
        super().__init__("LLMAnalyzerService")
        self._running = False
        self._http_client: Optional[httpx.AsyncClient] = None
        self._ollama_url: str = "http://localhost:11434"
        self._ollama_model: str = "llama3"
        self._cache_ttl: int = 3600  # Redis cache for LLM results

    async def start(self):
        self._running = True

        # Pull config from settings if available
        try:
            from ..config import settings
            self._ollama_url = getattr(settings, "OLLAMA_URL", self._ollama_url)
            self._ollama_model = getattr(settings, "OLLAMA_MODEL", self._ollama_model)
        except Exception:
            pass

        self._http_client = httpx.AsyncClient(timeout=60.0)
        logger.info(
            f"LLMAnalyzerService started. Ollama: {self._ollama_url}, model: {self._ollama_model}"
        )

        if nats_client.nc and nats_client.nc.is_connected:
            await nats_client.nc.subscribe(
                "n7.llm.analyze",
                cb=self._handle_analyze_request,
                queue="llm_analyzer",
            )
            logger.info("Subscribed to n7.llm.analyze")
        else:
            logger.warning("NATS not connected — LLMAnalyzerService subscription deferred.")

    async def stop(self):
        self._running = False
        if self._http_client:
            await self._http_client.aclose()
        logger.info("LLMAnalyzerService stopped.")

    # ------------------------------------------------------------------
    # NATS handler
    # ------------------------------------------------------------------

    async def _handle_analyze_request(self, msg):
        """
        Receives an alert bundle from ThreatCorrelatorService on n7.llm.analyze,
        generates/fetches a narrative, persists it to the DB, then forwards an
        enriched ProtoAlert to n7.alerts for DecisionEngineService.
        """
        try:
            bundle = json.loads(msg.data.decode())
            alert_id: str = bundle["alert_id"]
            reasoning: dict = bundle.get("reasoning", {})
            event_summaries: list = bundle.get("event_summaries", [])
            threat_score: int = bundle.get("threat_score", 0)
            severity: str = bundle.get("severity", "medium")
            event_ids: list = bundle.get("event_ids", [])
            affected_assets: list = bundle.get("affected_assets", [])

            logger.info(f"LLMAnalyzerService: analyzing alert {alert_id} (severity={severity})")

            # Check Redis cache first (idempotent re-analysis prevention)
            cache_key = f"n7:llm:narrative:{alert_id}"
            cached_raw = await redis_client.get(cache_key)
            if cached_raw:
                narrative_data = json.loads(cached_raw)
                logger.debug(f"LLM cache hit for alert {alert_id}")
            else:
                narrative_data = await self._generate_narrative(reasoning, event_summaries)
                await redis_client.set(cache_key, json.dumps(narrative_data), ex=self._cache_ttl)

            llm_narrative: str = narrative_data.get("narrative", "")
            llm_mitre_tactic: str = narrative_data.get("mitre_tactic", "")
            llm_mitre_technique: str = narrative_data.get("mitre_technique", "")

            # Persist LLM enrichment to the alerts table
            await self._persist_narrative(
                alert_id=alert_id,
                llm_narrative=llm_narrative,
                llm_mitre_tactic=llm_mitre_tactic,
                llm_mitre_technique=llm_mitre_technique,
            )

            # Build enriched reasoning for the alert proto
            enriched_reasoning = {
                **reasoning,
                "llm_narrative": llm_narrative,
                "llm_mitre_tactic": llm_mitre_tactic,
                "llm_mitre_technique": llm_mitre_technique,
            }

            # Republish to n7.alerts (Protobuf) for DecisionEngineService
            try:
                from schemas.alerts_pb2 import Alert as ProtoAlert
                proto_alert = ProtoAlert(
                    alert_id=alert_id,
                    created_at=datetime.utcnow().isoformat(),
                    event_ids=event_ids,
                    threat_score=threat_score,
                    severity=severity,
                    status="new",
                    verdict="pending",
                    reasoning=json.dumps(enriched_reasoning),
                    affected_assets=affected_assets,
                )
                if nats_client.nc and nats_client.nc.is_connected:
                    await nats_client.nc.publish("n7.alerts", proto_alert.SerializeToString())
                    logger.info(f"Published LLM-enriched alert {alert_id} to n7.alerts")
            except ImportError:
                # Protobuf schema not found — fall back to JSON publish
                if nats_client.nc and nats_client.nc.is_connected:
                    await nats_client.nc.publish(
                        "n7.alerts",
                        json.dumps({
                            "alert_id": alert_id,
                            "threat_score": threat_score,
                            "severity": severity,
                            "event_ids": event_ids,
                            "affected_assets": affected_assets,
                            "reasoning": enriched_reasoning,
                        }).encode(),
                    )

        except Exception as e:
            logger.error(f"LLMAnalyzerService error: {e}", exc_info=True)

    # ------------------------------------------------------------------
    # LLM call
    # ------------------------------------------------------------------

    async def _generate_narrative(self, reasoning: dict, event_summaries: list) -> dict:
        """
        Calls Ollama /api/generate with the alert context.
        Returns dict with keys: narrative, mitre_tactic, mitre_technique.
        Falls back to a structured rule-based summary if Ollama is unavailable.
        """
        prompt_context = json.dumps(
            {
                "rule": reasoning.get("rule"),
                "description": reasoning.get("description"),
                "source": reasoning.get("source"),
                "mitre_tactics": reasoning.get("mitre_tactics", []),
                "mitre_techniques": reasoning.get("mitre_techniques", []),
                "event_count": reasoning.get("count", 0),
                "is_multi_stage": reasoning.get("is_multi_stage", False),
                "event_summaries": event_summaries[:5],  # cap to 5 to manage token budget
            },
            indent=2,
        )
        full_prompt = f"{_SYSTEM_PROMPT}\n\nAlert bundle:\n{prompt_context}\n\nJSON response:"

        try:
            response = await self._http_client.post(
                f"{self._ollama_url}/api/generate",
                json={
                    "model": self._ollama_model,
                    "prompt": full_prompt,
                    "stream": False,
                    "format": "json",
                },
                timeout=45.0,
            )
            response.raise_for_status()
            raw_text = response.json().get("response", "{}")
            result = json.loads(raw_text)
            return {
                "narrative": result.get("narrative") or self._fallback_narrative(reasoning),
                "mitre_tactic": result.get("mitre_tactic", ""),
                "mitre_technique": result.get("mitre_technique", ""),
            }
        except Exception as e:
            logger.warning(f"Ollama unavailable ({type(e).__name__}: {e}) — using fallback narrative.")
            return {
                "narrative": self._fallback_narrative(reasoning),
                "mitre_tactic": ", ".join(reasoning.get("mitre_tactics", [])),
                "mitre_technique": ", ".join(reasoning.get("mitre_techniques", [])),
            }

    def _fallback_narrative(self, reasoning: dict) -> str:
        """Structured rule-based fallback when Ollama is not reachable."""
        rule = reasoning.get("rule", "Unknown rule")
        source = reasoning.get("source", "unknown source")
        count = reasoning.get("count", 0)
        tactics = ", ".join(reasoning.get("mitre_tactics", ["unknown"]))
        multi = " This is a multi-stage attack pattern." if reasoning.get("is_multi_stage") else ""
        return (
            f"Alert '{rule}' triggered for source {source}. "
            f"{count} matching event(s) observed.{multi} "
            f"Associated MITRE tactics: {tactics}. "
            f"Manual analyst review recommended."
        )

    # ------------------------------------------------------------------
    # DB persistence
    # ------------------------------------------------------------------

    async def _persist_narrative(
        self,
        alert_id: str,
        llm_narrative: str,
        llm_mitre_tactic: str,
        llm_mitre_technique: str,
    ):
        """Update the alert row with LLM-generated fields."""
        try:
            from sqlalchemy import update
            async with async_session_maker() as session:
                await session.execute(
                    update(AlertModel)
                    .where(AlertModel.alert_id == uuid.UUID(alert_id))
                    .values(
                        llm_narrative=llm_narrative,
                        llm_mitre_tactic=llm_mitre_tactic,
                        llm_mitre_technique=llm_mitre_technique,
                    )
                )
                await session.commit()
                logger.debug(f"LLM narrative persisted for alert {alert_id}")
        except Exception as e:
            logger.error(f"Failed to persist LLM narrative for alert {alert_id}: {e}", exc_info=True)
