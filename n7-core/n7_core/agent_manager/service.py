
import asyncio
import logging
from datetime import datetime, timedelta
from sqlalchemy import select, update
from ..service_manager.base_service import BaseService
from ..database.session import get_session
from ..models.agent import Agent
from ..config import settings

logger = logging.getLogger("n7-core.agent-manager")

class AgentManagerService(BaseService):
    """
    Agent Manager Service.
    Responsibility: Track agent lifecycle, health, and capability routing.
    Ref: TDD Section 4.5 Agent Manager Service
    """
    def __init__(self):
        super().__init__("AgentManagerService")
        self._running = False
        self._monitor_task = None

    async def start(self):
        self._running = True
        logger.info("AgentManagerService started.")
        self._monitor_task = asyncio.create_task(self._health_monitor_loop())

    async def stop(self):
        self._running = False
        if self._monitor_task:
            self._monitor_task.cancel()
            try:
                await self._monitor_task
            except asyncio.CancelledError:
                pass
        logger.info("AgentManagerService stopped.")

    async def _health_monitor_loop(self):
        """
        Background task to check agent health.
        Marks agents as unhealthy if they haven't sent a heartbeat recently.
        Ref: TDD FR-C031
        """
        while self._running:
            try:
                async for session in get_session():
                    # Threshold for unhealthy status (e.g., 3 * heartbeat_interval)
                    threshold = datetime.utcnow() - timedelta(seconds=90)
                    
                    stmt = (
                        update(Agent)
                        .where(Agent.last_heartbeat < threshold)
                        .where(Agent.status == "active")
                        .values(status="unhealthy")
                    )
                    result = await session.execute(stmt)
                    if result.rowcount > 0:
                        logger.warning(f"Marked {result.rowcount} agents as unhealthy.")
                        await session.commit()
            
            except Exception as e:
                logger.error(f"Error in health monitor loop: {e}")
            
            await asyncio.sleep(30) # Run every 30 seconds

    async def register_agent(self, agent_data: dict):
        """
        Registers or updates an agent.
        """
        async for session in get_session():
            try:
                # Upsert logic would go here
                pass
            except Exception as e:
                logger.error(f"Failed to register agent: {e}")
