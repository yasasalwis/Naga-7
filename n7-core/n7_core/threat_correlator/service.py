import json
import logging
import re
import uuid
from datetime import datetime, timedelta
from typing import Dict, List

# Protobuf schemas generated successfully
from schemas.alerts_pb2 import Alert as ProtoAlert
from schemas.events_pb2 import Event as ProtoEvent
# Import correlation rules
from .correlation_rules import CORRELATION_RULES
from ..database.redis import redis_client
from ..database.session import async_session_maker
from ..messaging.nats_client import nats_client
from ..models.alert import Alert as AlertModel
from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.threat-correlator")


class ThreatCorrelatorService(BaseService):
    """
    Threat Correlator Service.
    Responsibility: Correlate individual events/alerts into multi-stage attack patterns.
    Supports configurable correlation rules with MITRE ATT&CK mapping.
    
    Ref: TDD Section 4.3 / SRS 3.3 Threat Correlation
    """

    def __init__(self):
        super().__init__("ThreatCorrelatorService")
        self._running = False

        # Load correlation rules
        self.rules = CORRELATION_RULES
        logger.info(f"Loaded {len(self.rules)} correlation rules")

        # Event buffer for multi-stage correlation (keyed by source IP or asset)
        # Structure: {source_identifier: [list of events with timestamps]}
        self.event_buffer: Dict[str, List[Dict]] = {}

    async def start(self):
        self._running = True
        logger.info("ThreatCorrelatorService started.")

        # Subscribe to internal processed events
        if nats_client.nc and nats_client.nc.is_connected:
            await nats_client.nc.subscribe(
                "n7.internal.events",
                cb=self.handle_internal_event,
                queue="threat_correlator"
            )
            logger.info("Subscribed to n7.internal.events")
        else:
            logger.warning("NATS not connected, ThreatCorrelatorService waiting...")

    async def stop(self):
        self._running = False
        logger.info("ThreatCorrelatorService stopped.")

    async def handle_internal_event(self, msg):
        """Handle incoming events and apply correlation rules"""
        try:
            proto_event = ProtoEvent()
            proto_event.ParseFromString(msg.data)

            # Parse raw_data
            raw_data = json.loads(proto_event.raw_data) if isinstance(proto_event.raw_data,
                                                                      str) else proto_event.raw_data
            if isinstance(raw_data, bytes):
                raw_data = json.loads(raw_data.decode())

            event_class = proto_event.event_class
            source_ip = raw_data.get("source_ip", "unknown")

            # Store event in buffer for multi-stage correlation
            await self._buffer_event(source_ip, proto_event, raw_data)

            # Apply all correlation rules
            for rule_id, rule in self.rules.items():
                if "multi_stage" in rule:
                    # Multi-stage pattern matching
                    await self._check_multi_stage_pattern(rule_id, rule, source_ip)
                elif "pattern" in rule:
                    # Simple pattern matching
                    await self._check_simple_pattern(rule_id, rule, proto_event, raw_data)

        except Exception as e:
            logger.error(f"Error in ThreatCorrelator: {e}", exc_info=True)

    async def _buffer_event(self, source_identifier: str, proto_event, raw_data: Dict):
        """Buffer events for multi-stage correlation"""
        if source_identifier not in self.event_buffer:
            self.event_buffer[source_identifier] = []

        event_record = {
            "event_id": proto_event.event_id,
            "timestamp": datetime.fromisoformat(proto_event.timestamp) if isinstance(proto_event.timestamp,
                                                                                     str) else datetime.utcnow(),
            "event_class": proto_event.event_class,
            "raw_data": raw_data,
            "proto": proto_event
        }

        self.event_buffer[source_identifier].append(event_record)

        # Cleanup old events (keep last 1 hour)
        cutoff_time = datetime.utcnow() - timedelta(hours=1)
        self.event_buffer[source_identifier] = [
            e for e in self.event_buffer[source_identifier]
            if e["timestamp"] > cutoff_time
        ]

    async def _check_simple_pattern(self, rule_id: str, rule: Dict, proto_event, raw_data: Dict):
        """Check simple single-event pattern matching rules"""
        pattern = rule["pattern"]
        threshold = rule.get("threshold", 1)
        time_window = rule.get("time_window", 60)

        # Check if event matches pattern
        if not self._matches_pattern(pattern, proto_event.event_class, raw_data):
            return

        # Use Redis to track occurrences within time window
        source_ip = raw_data.get("source_ip", "unknown")
        key = f"n7:corr:{rule_id}:{source_ip}"

        count = await redis_client.incr(key)

        if count == 1:
            await redis_client.expire(key, time_window)

        if count >= threshold:
            logger.warning(f"Rule '{rule['name']}' triggered for {source_ip} (count={count})")
            await self._create_alert(
                rule_id=rule_id,
                rule=rule,
                source_identifier=source_ip,
                event_ids=[proto_event.event_id],
                count=count
            )
            # Reset counter after alert
            await redis_client.delete(key)

    async def _check_multi_stage_pattern(self, rule_id: str, rule: Dict, source_identifier: str):
        """Check multi-stage attack patterns"""
        if source_identifier not in self.event_buffer:
            return

        stages = rule["multi_stage"]
        buffered_events = self.event_buffer[source_identifier]

        # Check if all stages are satisfied
        matched_stages = []

        for stage in stages:
            min_occurrences = stage.get("min_occurrences", 1)
            within_seconds = stage.get("within_seconds")

            # Filter events matching this stage
            matching_events = []
            for event in buffered_events:
                if self._matches_stage(stage, event["event_class"], event["raw_data"]):
                    matching_events.append(event)

            # Check time window if specified
            if within_seconds:
                cutoff = datetime.utcnow() - timedelta(seconds=within_seconds)
                matching_events = [e for e in matching_events if e["timestamp"] > cutoff]

            # Check if minimum occurrences met
            if len(matching_events) >= min_occurrences:
                matched_stages.append({
                    "stage": stage,
                    "events": matching_events[:min_occurrences]
                })

        # If all stages matched, create alert
        if len(matched_stages) == len(stages):
            event_ids = []
            for stage_data in matched_stages:
                event_ids.extend([e["event_id"] for e in stage_data["events"]])

            logger.warning(f"Multi-stage rule '{rule['name']}' triggered for {source_identifier}")
            await self._create_alert(
                rule_id=rule_id,
                rule=rule,
                source_identifier=source_identifier,
                event_ids=event_ids,
                count=len(event_ids),
                is_multi_stage=True
            )

            # Clear buffer for this source to avoid duplicate alerts
            self.event_buffer[source_identifier] = []

    def _matches_pattern(self, pattern: Dict, event_class: str, raw_data: Dict) -> bool:
        """Check if event matches a simple pattern"""
        # Check event_class
        if pattern.get("event_class") and pattern["event_class"] != event_class:
            return False

        # Check all pattern fields
        for key, value in pattern.items():
            if key == "event_class":
                continue

            if key.endswith("_threshold"):
                # Special handling for numeric thresholds
                field_name = key.replace("_threshold", "")
                if field_name not in raw_data or raw_data[field_name] < value:
                    return False
            elif key.endswith("_regex"):
                # Regex matching
                field_name = key.replace("_regex", "")
                if field_name not in raw_data:
                    return False
                if not re.search(value, str(raw_data[field_name]), re.IGNORECASE):
                    return False
            else:
                # Exact match
                if raw_data.get(key) != value:
                    return False

        return True

    def _matches_stage(self, stage: Dict, event_class: str, raw_data: Dict) -> bool:
        """Check if event matches a multi-stage pattern stage"""
        # Check event_class
        if stage.get("event_class") and stage["event_class"] != event_class:
            return False

        # Check contains patterns
        for key, patterns in stage.items():
            if key.endswith("_contains"):
                field_name = key.replace("_contains", "")
                if field_name not in raw_data:
                    return False

                raw_value = str(raw_data[field_name]).lower()
                if not any(pattern.lower() in raw_value for pattern in patterns):
                    return False

        # Check other fields
        for key, value in stage.items():
            if key in ["min_occurrences", "within_seconds", "event_class"] or key.endswith("_contains"):
                continue

            if raw_data.get(key) != value:
                return False

        return True

    # Cooldown window (seconds) before the same rule+source triggers another LLM analysis.
    # This prevents alert floods when a persistent condition (e.g. high CPU) keeps firing.
    ALERT_COOLDOWN = 300  # 5 minutes

    async def _create_alert(
            self,
            rule_id: str,
            rule: Dict,
            source_identifier: str,
            event_ids: List[str],
            count: int,
            is_multi_stage: bool = False
    ):
        """Create and publish an alert, suppressing LLM re-analysis during cooldown."""
        # --- Cooldown guard -----------------------------------------------------------
        # Persist an alert entry every time the rule fires so the DB reflects reality,
        # but only send to the LLM when the cooldown key is absent.  This prevents
        # flooding the LLM with the same recurring condition (e.g. CPU always high).
        cooldown_key = f"n7:alert_cooldown:{rule_id}:{source_identifier}"
        in_cooldown = await redis_client.get(cooldown_key)

        alert_id = str(uuid.uuid4())
        severity = rule.get("severity", "medium")

        reasoning = {
            "rule": rule["name"],
            "description": rule["description"],
            "count": count,
            "source": source_identifier,
            "mitre_tactics": rule.get("mitre_tactics", []),
            "mitre_techniques": rule.get("mitre_techniques", []),
            "is_multi_stage": is_multi_stage
        }

        # Calculate threat score based on severity and MITRE mapping
        threat_score = self._calculate_threat_score(severity, is_multi_stage, rule_id=rule_id)

        # Create protobuf alert
        proto_alert = ProtoAlert(
            alert_id=alert_id,
            created_at=datetime.utcnow().isoformat(),
            event_ids=event_ids,
            threat_score=threat_score,
            severity=severity,
            status="new",
            verdict="pending",
            reasoning=json.dumps(reasoning),
            affected_assets=[source_identifier]
        )

        # Persist alert to database
        async with async_session_maker() as session:
            db_alert = AlertModel(
                alert_id=uuid.UUID(alert_id),
                created_at=datetime.utcnow(),
                event_ids=event_ids,
                threat_score=threat_score,
                severity=severity,
                status="new",
                verdict="pending",
                affected_assets=[source_identifier],
                reasoning=reasoning
            )
            session.add(db_alert)
            await session.commit()

        # Route through LLM Analyzer instead of publishing directly to n7.alerts.
        # LLMAnalyzerService enriches the alert with a narrative then forwards to n7.alerts.
        if in_cooldown:
            # Same rule+source already analyzed recently — skip LLM to prevent flooding.
            # The alert is already persisted to DB above; just log and return.
            logger.info(
                f"Alert cooldown active for rule '{rule['name']}' / source '{source_identifier}' "
                f"— skipping LLM re-analysis until cooldown expires."
            )
            return

        # Set cooldown BEFORE publishing so parallel firings don't race through
        await redis_client.set(cooldown_key, "1", ex=self.ALERT_COOLDOWN)

        llm_bundle = {
            "alert_id": alert_id,
            "reasoning": reasoning,
            "threat_score": threat_score,
            "severity": severity,
            "event_ids": event_ids,
            "affected_assets": [source_identifier],
            "event_summaries": self._build_event_summaries(source_identifier, event_ids),
        }
        if nats_client.nc and nats_client.nc.is_connected:
            await nats_client.nc.publish("n7.llm.analyze", json.dumps(llm_bundle).encode())
            logger.info(f"Sent alert bundle {alert_id} to n7.llm.analyze for rule '{rule['name']}'")

    def _build_event_summaries(self, source_identifier: str, event_ids: List[str]) -> List[Dict]:
        """Return abbreviated summaries (up to 5) of buffered events matching given IDs."""
        summaries = []
        event_id_set = set(event_ids)
        buffered = self.event_buffer.get(source_identifier, [])
        for record in buffered:
            if record.get("event_id") in event_id_set:
                summaries.append({
                    "event_id": record.get("event_id"),
                    "event_class": record.get("event_class"),
                    "timestamp": record.get("timestamp").isoformat() if record.get("timestamp") else None,
                    "raw_data": record.get("raw_data", {}),
                })
            if len(summaries) >= 5:
                break
        return summaries

    def _calculate_threat_score(self, severity: str, is_multi_stage: bool, rule_id: str = "") -> int:
        """Calculate threat score based on severity and attack complexity."""
        # Honeytoken access is always maximum confidence (100)
        if rule_id == "honeytoken_access":
            return 100

        base_scores = {
            "critical": 90,
            "high": 75,
            "medium": 50,
            "low": 25,
            "info": 10
        }

        score = base_scores.get(severity, 50)

        # Increase score for multi-stage attacks
        if is_multi_stage:
            score = min(100, score + 10)

        return score
