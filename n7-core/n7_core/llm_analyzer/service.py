import json
import logging
import uuid
from datetime import datetime
from typing import Optional

import httpx

from ..config import settings
from ..database.redis import redis_client
from ..database.session import async_session_maker
from ..messaging.nats_client import nats_client
from ..models.alert import Alert as AlertModel
from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.llm-analyzer")

_EVENT_PROMPT = (
    "You are a cybersecurity AI. Analyze the following raw event data from a Sentinel. "
    "Provide a brief 1-2 sentence recommendation or insight regarding this single event. "
    "Focus on whether it looks suspicious or benign. Return only plain text."
)

# System prompt sent to Ollama before each alert bundle
_SYSTEM_PROMPT = (
    "You are a senior cybersecurity analyst AI assistant. "
    "Analyze the security alert bundle provided and return ONLY a JSON object "
    "(no markdown, no explanation outside the JSON) with exactly four keys:\n"
    "  \"narrative\": a concise 2-4 sentence plain-English description of the attack,\n"
    "  \"mitre_tactic\": the most relevant MITRE ATT&CK tactic name (e.g. 'Lateral Movement'),\n"
    "  \"mitre_technique\": the most relevant technique ID and name "
    "(e.g. 'T1021 - Remote Services'),\n"
    "  \"remediation\": a numbered list of 3-5 specific, actionable remediation steps as a single "
    "string with steps separated by newlines "
    "(e.g. '1. Isolate the affected host immediately.\\n2. Reset compromised credentials.\\n"
    "3. Review firewall rules for unauthorized outbound connections.').\n"
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
        self._ollama_url: str = settings.OLLAMA_URL
        self._ollama_model: str = settings.OLLAMA_MODEL
        self._cache_ttl: int = 3600  # Redis cache for LLM results

    async def start(self):
        self._running = True
        self._http_client = httpx.AsyncClient(timeout=60.0)
        logger.info(
            f"LLMAnalyzerService started. Ollama: {self._ollama_url}, model: {self._ollama_model}"
        )

        # Verify Ollama is reachable before accepting alert traffic
        await self._startup_health_check()

        if nats_client.nc and nats_client.nc.is_connected:
            await nats_client.nc.subscribe(
                "n7.llm.analyze",
                cb=self._handle_analyze_request,
                queue="llm_analyzer",
            )
            await nats_client.nc.subscribe(
                "n7.internal.events",
                cb=self._handle_event_analyze_request,
                queue="llm_analyzer_events",
            )
            logger.info("Subscribed to n7.llm.analyze and n7.internal.events")
        else:
            logger.warning("NATS not connected — LLMAnalyzerService subscription deferred.")

    async def _startup_health_check(self) -> bool:
        """
        Probes Ollama at service startup.
        Returns True if reachable, False otherwise.
        Logs a prominent warning if unavailable so operators know LLM is degraded.
        """
        healthy = await self.check_llm_health()
        if healthy:
            logger.info(
                f"LLM health check PASSED — Ollama is reachable at {self._ollama_url} "
                f"with model '{self._ollama_model}'."
            )
        else:
            logger.warning(
                "LLM health check FAILED — Ollama is not reachable at %s. "
                "LLMAnalyzerService will use rule-based fallback narratives until Ollama becomes available. "
                "Check OLLAMA_URL and ensure the Ollama service is running.",
                self._ollama_url,
            )
        return healthy

    async def check_llm_health(self) -> bool:
        """
        Pings the Ollama /api/tags endpoint to confirm the service is up and the
        configured model is available.  Returns True on success, False on any error.
        Used by the startup probe and the /health API endpoint.
        """
        if self._http_client is None:
            return False
        try:
            response = await self._http_client.get(
                f"{self._ollama_url}/api/tags",
                timeout=10.0,
            )
            response.raise_for_status()
            tags_data = response.json()
            available_models = [m.get("name", "") for m in tags_data.get("models", [])]
            # Accept both exact match and name-prefix match (e.g. "llama3" matches "llama3:latest")
            model_found = any(
                m == self._ollama_model or m.startswith(f"{self._ollama_model}:")
                for m in available_models
            )
            if not model_found:
                logger.warning(
                    "Ollama is reachable but model '%s' is not in the available list: %s. "
                    "Pull it with: ollama pull %s",
                    self._ollama_model,
                    available_models,
                    self._ollama_model,
                )
            return True  # Ollama itself is up; caller decides what to do with missing model
        except Exception as e:
            logger.debug("LLM health probe failed: %s: %s", type(e).__name__, e)
            return False

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
            llm_remediation: str = narrative_data.get("remediation", "")

            # Persist LLM enrichment to the alerts table
            await self._persist_narrative(
                alert_id=alert_id,
                llm_narrative=llm_narrative,
                llm_mitre_tactic=llm_mitre_tactic,
                llm_mitre_technique=llm_mitre_technique,
                llm_remediation=llm_remediation,
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

    async def _handle_event_analyze_request(self, msg):
        """
        Receives raw events and generates a brief LLM recommendation,
        updating the Event record's enrichments.
        """
        import asyncio
        import uuid
        try:
            try:
                from schemas.events_pb2 import Event as ProtoEvent
                proto_event = ProtoEvent()
                proto_event.ParseFromString(msg.data)
                event_id = proto_event.event_id
                raw_data = json.loads(proto_event.raw_data) if proto_event.raw_data else {}
            except Exception:
                data = json.loads(msg.data.decode())
                event_id = data.get("event_id")
                raw_data = data.get("raw_data", {})
                
            if not event_id:
                return

            # Wait for EventPipeline to flush buffer
            await asyncio.sleep(1.5)

            prompt_context = json.dumps(raw_data, indent=2)
            full_prompt = f"{_EVENT_PROMPT}\n\nEvent Data:\n{prompt_context}\n\nInsight:"

            try:
                response = await self._http_client.post(
                    f"{self._ollama_url}/api/generate",
                    json={
                        "model": self._ollama_model,
                        "prompt": full_prompt,
                        "stream": False,
                    },
                    timeout=20.0,
                )
                response.raise_for_status()
                llm_response = response.json().get("response", "").strip()
            except Exception as e:
                logger.warning(f"Ollama unavailable for event {event_id}: {e}")
                llm_response = "Unable to reach LLM for recommendation."

            from sqlalchemy import select, update
            from ..database.session import async_session_maker
            from ..models.event import Event as EventModel
            
            async with async_session_maker() as session:
                result = await session.execute(
                    select(EventModel).where(EventModel.event_id == uuid.UUID(event_id))
                )
                event = result.scalar_one_or_none()
                if event:
                    new_enrichments = dict(event.enrichments or {})
                    new_enrichments["llm_recommendation"] = llm_response
                    await session.execute(
                        update(EventModel)
                        .where(EventModel.event_id == uuid.UUID(event_id))
                        .values(enrichments=new_enrichments)
                    )
                    await session.commit()
                    logger.debug(f"Event {event_id} enriched with LLM recommendation.")

        except Exception as e:
            logger.error(f"Error in event LLM analysis: {e}", exc_info=True)

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
                "remediation": result.get("remediation", ""),
            }
        except Exception as e:
            logger.warning(f"Ollama unavailable ({type(e).__name__}: {e}) — using fallback narrative.")
            return {
                "narrative": self._fallback_narrative(reasoning),
                "mitre_tactic": ", ".join(reasoning.get("mitre_tactics", [])),
                "mitre_technique": ", ".join(reasoning.get("mitre_techniques", [])),
                "remediation": self._fallback_remediation(reasoning),
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

    def _fallback_remediation(self, reasoning: dict) -> str:
        """Rule-based fallback remediation steps when Ollama is not reachable."""
        rule = reasoning.get("rule", "Unknown rule")
        return (
            f"1. Investigate the triggered rule: '{rule}'.\n"
            "2. Review system and application logs on all affected hosts for anomalous activity.\n"
            "3. Isolate any confirmed compromised hosts from the network pending investigation.\n"
            "4. Apply relevant firewall rules or access control restrictions as a precaution.\n"
            "5. Escalate to your security team and document findings in your incident response system."
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
        llm_remediation: str = "",
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
                        llm_remediation=llm_remediation,
                    )
                )
                await session.commit()
                logger.debug(f"LLM narrative persisted for alert {alert_id}")
        except Exception as e:
            logger.error(f"Failed to persist LLM narrative for alert {alert_id}: {e}", exc_info=True)
