import logging
from abc import ABC, abstractmethod

logger = logging.getLogger("n7-sentinel.probes")


class BaseProbe(ABC):
    """
    Abstract Base Class for Sentinel Probes.
    """

    def __init__(self, name: str, interval: int = 10):
        self.name = name
        self.interval = interval

    @abstractmethod
    async def collect(self) -> dict:
        """
        Collects data from the target.
        Returns a dictionary of metrics/events.
        """
        pass
