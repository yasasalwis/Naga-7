
from abc import ABC, abstractmethod

class BaseService(ABC):
    """
    Base class for all N7-Core services.
    Enforces the Service protocol expected by ServiceManager.
    """
    def __init__(self, name: str):
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @abstractmethod
    async def start(self):
        """Asynchronously start the service."""
        pass

    @abstractmethod
    async def stop(self):
        """Asynchronously stop the service."""
        pass
