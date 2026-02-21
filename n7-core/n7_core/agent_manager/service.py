import json
import logging
from datetime import datetime, UTC

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
            await nats_client.nc.subscribe(
                "n7.node.metadata.>",
                cb=self.handle_node_metadata,
                queue="agent_manager"
            )
            logger.info("Subscribed to n7.heartbeat.> and n7.node.metadata.>")
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
                    agent.last_heartbeat = datetime.now(UTC)
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
                        last_heartbeat=datetime.now(UTC),
                        resource_usage=data.get("resource_usage", {})
                    )
                    session.add(agent)

                await session.commit()
                logger.debug(f"Processed heartbeat for agent {agent_id}")

        except Exception as e:
            logger.error(f"Error processing heartbeat: {e}")

    async def handle_node_metadata(self, msg):
        """Persist rich node metadata published by a Sentinel on restart."""
        try:
            data = json.loads(msg.data.decode())
            agent_id = data.get("agent_id")
            if not agent_id:
                logger.warning("handle_node_metadata: missing agent_id in message")
                return

            # Store everything except agent_id itself as the metadata blob
            metadata = {k: v for k, v in data.items() if k != "agent_id"}

            async with async_session_maker() as session:
                stmt = select(Agent).where(Agent.id == agent_id)
                result = await session.execute(stmt)
                agent = result.scalar_one_or_none()

                if agent:
                    agent.node_metadata = metadata
                    await session.commit()
                    logger.info(
                        f"Stored node metadata for agent {agent_id}: "
                        f"host={metadata.get('hostname')}, OS={metadata.get('os_name')} "
                        f"{metadata.get('kernel_version')}, "
                        f"CPU={metadata.get('cpu_cores')} cores, "
                        f"RAM={metadata.get('ram_total_mb')} MB"
                    )
                else:
                    logger.warning(
                        f"handle_node_metadata: agent {agent_id} not found in DB — "
                        "metadata discarded (agent may not have registered yet)"
                    )

        except Exception as e:
            logger.error(f"Error processing node metadata: {e}")
