import asyncio
import logging
from typing import AsyncIterator, Dict, Any

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

    async def initialize(self, config: dict) -> None:
        logger.info("Initializing ProcessProbe...")
        # Initial snapshot
        self._known_pids = set(psutil.pids())

    async def observe(self) -> AsyncIterator[Dict[str, Any]]:
        self._running = True
        logger.info("ProcessProbe started observing.")

        while self._running:
            current_pids = set(psutil.pids())
            new_pids = current_pids - self._known_pids

            for pid in new_pids:
                try:
                    p = psutil.Process(pid)
                    event_data = {
                        "event_class": "process",
                        "raw_data": {
                            "pid": pid,
                            "name": p.name(),
                            "cmdline": p.cmdline(),
                            "username": p.username(),
                            "create_time": p.create_time(),
                            "ppid": p.ppid()
                        }
                    }
                    yield event_data
                except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                    continue

            self._known_pids = current_pids
            await asyncio.sleep(1.0)  # Polling interval

    async def shutdown(self) -> None:
        self._running = False
        logger.info("ProcessProbe shutdown.")
