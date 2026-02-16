
import psutil
import asyncio
from typing import Dict, Any
from .base import BaseProbe

class SystemProbe(BaseProbe):
    """
    Probe for system metrics (CPU, Memory, Disk).
    """
    def __init__(self, interval: int = 10):
        super().__init__("SystemProbe", interval)

    async def collect(self) -> Dict[str, Any]:
        """
        Collects system metrics.
        """
        cpu_percent = psutil.cpu_percent(interval=None)
        memory = psutil.virtual_memory()
        disk = psutil.disk_usage('/')
        
        return {
            "cpu_percent": cpu_percent,
            "memory_percent": memory.percent,
            "disk_percent": disk.percent
        }
