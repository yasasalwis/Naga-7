
import asyncio
import logging
from typing import List, Protocol

logger = logging.getLogger("n7-core.service-manager")

class Service(Protocol):
    async def start(self):
        ...

    async def stop(self):
        ...
        
    @property
    def name(self) -> str:
        ...

class ServiceManager:
    """
    Manages the lifecycle of N7-Core services.
    Ref: TDD Section 4.1 Core Service Decomposition
    """
    def __init__(self):
        self.services: List[Service] = []
        self._running = False

    def register(self, service: Service):
        self.services.append(service)
        logger.info(f"Registered service: {service.name}")

    async def start_all(self):
        logger.info("Starting all services...")
        self._running = True
        # In a real implementation, we might want to start these in a specific order or in parallel
        # For now, start sequentially
        for service in self.services:
            try:
                logger.info(f"Starting {service.name}...")
                await service.start()
                logger.info(f"Started {service.name}")
            except Exception as e:
                logger.error(f"Failed to start {service.name}: {e}")
                # Depending on resilience policy, we might want to stop everything or continue
                raise

    async def stop_all(self):
        logger.info("Stopping all services...")
        self._running = False
        # Stop in reverse order of start
        for service in reversed(self.services):
            try:
                logger.info(f"Stopping {service.name}...")
                await service.stop()
                logger.info(f"Stopped {service.name}")
            except Exception as e:
                logger.error(f"Failed to stop {service.name}: {e}")
