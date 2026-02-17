
import asyncio
import logging
import aiohttp
from .config import settings
from .graph import build_sentinel_graph, AgentState

logger = logging.getLogger("n7-sentinel.agent-runtime")

class AgentRuntimeService:
    """
    Agent Runtime Service.
    Responsibility: Handle registration, heartbeat, and configuration sync with Core.
    Ref: TDD Section 5.1 Sentinel Process Model
    """
    def __init__(self):
        self._running = False
        self._session = None
        self._token = None
        self._token = None
        self._agent_id = None
        self._graph = None

    async def start(self):
        self._running = True
        logger.info("AgentRuntimeService started.")
        self._session = aiohttp.ClientSession()
        
        # Authenticate with Core
        await self._authenticate()
        
        # Build Graph
        self._graph = build_sentinel_graph()
        
        # Start Heartbeat Loop
        asyncio.create_task(self._heartbeat_loop())
        # Start Agent Graph Loop
        asyncio.create_task(self._agent_loop())

    async def stop(self):
        self._running = False
        if self._session:
            await self._session.close()
        logger.info("AgentRuntimeService stopped.")

    async def _agent_loop(self):
        """
        Periodically runs the agent graph.
        """
        logger.info("Starting Agent Graph Loop...")
        while self._running:
            try:
                if self._graph:
                    initial_state = AgentState(
                        messages=[], 
                        metrics={}, 
                        anomalies=[], 
                        status="idle"
                    )
                    # Invoke graph
                    result = await self._graph.ainvoke(initial_state)
                    logger.debug(f"Agent Graph Result: {result.get('status')} - {result.get('messages')}")
            except Exception as e:
                logger.error(f"Error in Agent Graph Loop: {e}")
            
            await asyncio.sleep(10) # Run every 10 seconds

    async def _authenticate(self):
        """
        Authenticates with Core to register and get ID.
        """
        try:
            logger.info("Authenticating with Core...")
            payload = {
                "agent_type": settings.AGENT_TYPE,
                "agent_subtype": settings.AGENT_SUBTYPE,
                "zone": settings.ZONE,
                "capabilities": ["system_probe", "file_integrity"], # Dynamic in real world
                "metadata": {"hostname": "localhost"}
            }
            # Add timeout
            timeout = aiohttp.ClientTimeout(total=10)
            async with self._session.post(f"{settings.CORE_API_URL}/agents/register", json=payload, timeout=timeout) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._agent_id = data.get("id")
                    # self._token = data.get("token") # If using token auth
                    logger.info(f"Registered with Core. Agent ID: {self._agent_id}")
                else:
                    logger.error(f"Registration failed: {resp.status} {await resp.text()}")

        except Exception as e:
            logger.error(f"Authentication failed: {e}")

    async def _heartbeat_loop(self):
        """
        Sends periodic heartbeats to Core.
        """
        while self._running:
            try:
                if hasattr(self, '_agent_id') and self._agent_id:
                    payload = {
                        "agent_id": self._agent_id,
                        "status": "active",
                        "resource_usage": {"cpu": 10, "memory": 20} # Placeholder
                    }
                    # headers = {"Authorization": f"Bearer {self._token}"}
                    async with self._session.post(f"{settings.CORE_API_URL}/agents/heartbeat", json=payload) as resp:
                         if resp.status != 200:
                             logger.warning(f"Heartbeat failed: {resp.status}")
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
            
            await asyncio.sleep(30)
