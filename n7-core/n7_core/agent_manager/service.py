import json
import logging
from datetime import datetime

from sqlalchemy import select

from ..database.session import async_session_maker
from ..messaging.nats_client import nats_client
from ..models.agent import Agent
from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.agent-manager")


class AgentManagerService(BaseService):
    """
    Agent Manager Service.
    Responsibility: Track agent lifecycle, health, and capability routing.
    """

    def __init__(self):
        super().__init__("AgentManagerService")
        self._running = False

    async def start(self):
        self._running = True
        logger.info("AgentManagerService started.")

        if nats_client.nc.is_connected:
            await nats_client.nc.subscribe(
                "n7.heartbeat.>",
                cb=self.handle_heartbeat,
                queue="agent_manager"
            )
            logger.info("Subscribed to n7.heartbeat.>")
        else:
            logger.warning("NATS not connected.")

    async def stop(self):
        self._running = False
        logger.info("AgentManagerService stopped.")

    async def handle_heartbeat(self, msg):
        try:
            data = json.loads(msg.data.decode())
            agent_id = data.get("agent_id")

            # Upsert agent status
            async with async_session_maker() as session:
                stmt = select(Agent).where(Agent.id == agent_id)
                result = await session.execute(stmt)
                agent = result.scalar_one_or_none()

                if agent:
                    agent.last_heartbeat = datetime.utcnow()
                    agent.status = data.get("status", "active")
                    agent.resource_usage = data.get("resource_usage", {})
                    # Update config_version if reported?
                else:
                    # New agent registration (implicitly via heartbeat for MVP)
                    agent = Agent(
                        id=agent_id,
                        agent_type=data.get("agent_type", "unknown"),
                        agent_subtype=data.get("agent_subtype", "unknown"),
                        capabilities=data.get("capabilities", []),
                        zone=data.get("zone", "default"),
                        status=data.get("status", "active"),
                        last_heartbeat=datetime.utcnow(),
                        resource_usage=data.get("resource_usage", {})
                    )
                    session.add(agent)

                await session.commit()
                logger.debug(f"Processed heartbeat for agent {agent_id}")

        except Exception as e:
            logger.error(f"Error processing heartbeat: {e}")
