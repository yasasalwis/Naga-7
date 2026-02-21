import logging
from typing import Dict, Any

from ..agent_runtime.config import settings

logger = logging.getLogger("n7-sentinel.detection-engine")


class DetectionEngineService:
    """
    Detection Engine Service.
    Responsibility: Analyze collected data for anomalies/signatures locally.
    Ref: TDD Section 5.1 Sentinel Process Model
    """

    def __init__(self, event_emitter):
        self._running = False
        self.event_emitter = event_emitter

    async def start(self):
        self._running = True
        logger.info("DetectionEngineService started.")

    async def stop(self):
        self._running = False
        logger.info("DetectionEngineService stopped.")

    async def analyze(self, probe_name: str, data: Dict[str, Any]):
        """
        Analyzes data from a probe and emits structured events for Core's LLM pipeline.
        Supports SystemProbe, ProcessProbe, NetworkProbe, and FileProbe.
        """
        if probe_name == "SystemProbe":
            thresholds = settings.DETECTION_THRESHOLDS
            cpu_t  = float(thresholds.get("cpu_threshold", 80))
            mem_t  = float(thresholds.get("mem_threshold", 85))
            disk_t = float(thresholds.get("disk_threshold", 90))
            checks = [
                (data.get("cpu_percent", 0) > cpu_t,   "high", f"High CPU Usage (threshold={cpu_t}%)"),
                (data.get("memory_percent", 0) > mem_t, "high", f"High Memory Usage (threshold={mem_t}%)"),
                (data.get("disk_percent", 0) > disk_t,  "high", f"High Disk Usage (threshold={disk_t}%)"),
            ]
            for condition, severity, description in checks:
                if condition:
                    logger.warning(f"{description} detected!")
                    await self.event_emitter.emit({
                        "event_class": "endpoint",
                        "severity":    severity,
                        "raw_data":    {"description": description, **data},
                    })

        elif probe_name == "ProcessProbe":
            await self.event_emitter.emit({
                "event_class": "process",
                "severity":    "informational",
                "raw_data":    data,
            })

        elif probe_name == "NetworkProbe":
            raw = data.get("raw_data", data)
            severity = "high" if raw.get("flags") == "S" else "informational"
            if severity == "high":
                logger.warning(f"Port scan attempt detected from {raw.get('src', 'unknown')}")
            await self.event_emitter.emit({
                "event_class": "network",
                "severity":    severity,
                "raw_data":    raw,
            })

        elif probe_name == "FileProbe":
            await self.event_emitter.emit({
                "event_class": "file_change",
                "severity":    "medium",
                "raw_data":    data,
            })
