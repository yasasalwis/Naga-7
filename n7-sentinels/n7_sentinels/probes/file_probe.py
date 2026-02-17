import asyncio
import logging
import threading
from typing import AsyncIterator, Dict, Any
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

logger = logging.getLogger("n7-sentinel.probes.file")

class FileProbe(FileSystemEventHandler):
    """
    File Integrity Probe.
    Responsibility: Monitor file system changes in critical directories.
    """
    def __init__(self):
        self.probe_type = "file_monitor"
        self._running = False
        self._queue = asyncio.Queue()
        self._observer = Observer()
        self._loop = None

    async def initialize(self, config: dict) -> None:
        logger.info("Initializing FileProbe...")
        self.paths = config.get("paths", ["/tmp"]) # Default to /tmp for safety in dev
        self._loop = asyncio.get_running_loop()

    def on_any_event(self, event):
        if not self._running:
            return
        
        try:
            event_data = {
                "event_class": "file_change",
                "raw_data": {
                    "event_type": event.event_type,
                    "src_path": event.src_path,
                    "is_directory": event.is_directory
                }
            }
            if not event.is_directory:
                 # Filter noise if needed
                 pass

            if self._loop:
                asyncio.run_coroutine_threadsafe(self._queue.put(event_data), self._loop)

        except Exception as e:
            logger.error(f"Error processing file event: {e}")

    async def observe(self) -> AsyncIterator[Dict[str, Any]]:
        self._running = True
        logger.info(f"FileProbe started observing: {self.paths}")
        
        for path in self.paths:
            try:
                self._observer.schedule(self, path, recursive=True)
            except Exception as e:
                logger.error(f"Failed to watch {path}: {e}")

        self._observer.start()
        
        try:
            while self._running:
                try:
                    event = await asyncio.wait_for(self._queue.get(), timeout=1.0)
                    yield event
                except asyncio.TimeoutError:
                    continue
        finally:
            self._observer.stop()
            self._observer.join()

    async def shutdown(self) -> None:
        self._running = False
        logger.info("FileProbe shutdown.")
