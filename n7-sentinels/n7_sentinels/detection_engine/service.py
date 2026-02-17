import logging
from typing import Dict, Any

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
        Analyzes data from a probe.
        """
        # Simple threshold rule for demonstration
        if probe_name == "SystemProbe":
            if data.get("cpu_percent", 0) > 90:
                logger.warning("High CPU detected!")
                event = {
                    "class": "system",
                    "severity": "high",
                    "description": "High CPU Usage",
                    "data": data
                }
                await self.event_emitter.emit(event)
