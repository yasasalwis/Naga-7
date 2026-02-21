import asyncio
import logging
from typing import AsyncIterator, Dict, Any, List

import psutil

logger = logging.getLogger("n7-sentinel.probes.process")


class ProcessProbe:
    """
    Process Probe.
    Responsibility: Monitor process creation and resource usage.
    """

    def __init__(self):
        self.probe_type = "process_monitor"
        self._running = False
        self._known_pids = set()

        # Simple predefined rules for anomalies
        self._suspicious_paths = ["/tmp/", "/dev/shm/", "C:\\Windows\\Temp\\"]
        self._suspicious_commands = ["curl", "wget", "nc", "netcat", "bash -i", "sh -i", "powershell -enc"]

    async def initialize(self, config: dict) -> None:
        logger.info("Initializing ProcessProbe...")
        # Initial snapshot
        self._known_pids = set(psutil.pids())

    def _evaluate_anomaly(self, p: psutil.Process, cmdline: List[str]) -> Dict[str, Any]:
        """
        Evaluates a process for suspicious behavior based on path and command line.
        Returns a dictionary with anomaly details if found, or None.
        """
        anomaly_reasons = []
        severity = "info"  # Default

        try:
            exe_path = p.exe().lower()
            if any(suspicious_path in exe_path for suspicious_path in self._suspicious_paths):
                anomaly_reasons.append(f"Executing from suspicious path: {exe_path}")
                severity = "high"
        except (psutil.AccessDenied, psutil.ZombieProcess):
            pass # Can't access exe path, skip path check

        cmdline_str = " ".join(cmdline).lower()
        if any(suspicious_cmd in cmdline_str for suspicious_cmd in self._suspicious_commands):
            anomaly_reasons.append(f"Suspicious command line detected: {cmdline_str}")
            severity = "high"

        if anomaly_reasons:
            return {
                "is_anomaly": True,
                "reasons": anomaly_reasons,
                "severity": severity
            }
        return {"is_anomaly": False, "severity": "info"}

    async def observe(self) -> AsyncIterator[Dict[str, Any]]:
        self._running = True
        logger.info("ProcessProbe started observing.")

        while self._running:
            current_pids = set(psutil.pids())
            new_pids = current_pids - self._known_pids

            for pid in new_pids:
                try:
                    p = psutil.Process(pid)
                    cmdline = p.cmdline()
                    
                    anomaly_eval = self._evaluate_anomaly(p, cmdline)

                    event_data = {
                        "event_class": "process",
                        "severity": anomaly_eval["severity"], # Set severity based on anomaly eval
                        "raw_data": {
                            "pid": pid,
                            "name": p.name(),
                            "cmdline": cmdline,
                            "username": p.username(),
                            "create_time": p.create_time(),
                            "ppid": p.ppid()
                        }
                    }

                    if anomaly_eval["is_anomaly"]:
                        event_data["raw_data"]["anomaly_details"] = anomaly_eval["reasons"]

                    yield event_data
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            self._known_pids = current_pids
            await asyncio.sleep(1.0)  # Polling interval

    async def shutdown(self) -> None:
        self._running = False
        logger.info("ProcessProbe shutdown.")
