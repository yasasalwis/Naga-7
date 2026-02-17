import asyncio
import logging
import os
import secrets
from pathlib import Path

import aiohttp

from .config import settings
from .graph import build_striker_graph, AgentState

logger = logging.getLogger("n7-striker.agent-runtime")


class AgentRuntimeService:
    """
    Agent Runtime Service.
    Responsibility: Handle registration, heartbeat, and auth with Core.
    """

    def __init__(self):
        self._running = False
        self._session = None
        self._api_key = None  # Agent's unique API key
        self._agent_id = None
        self._graph = None

        # Load or generate API key on initialization
        self._api_key = self._load_or_generate_api_key()

    async def start(self):
        self._running = True
        logger.info("AgentRuntimeService started.")
        self._session = aiohttp.ClientSession()
        # Build Graph
        self._graph = build_striker_graph()

        # Start Heartbeat Loop
        asyncio.create_task(self._heartbeat_loop())
        # Start Agent Graph Loop
        asyncio.create_task(self._agent_loop())

    async def stop(self):
        self._running = False
        if self._session:
            await self._session.close()
        logger.info("AgentRuntimeService stopped.")

    def _load_or_generate_api_key(self) -> str:
        """
        Load existing API key from file, or generate a new secure one.
        Returns the API key string.
        """
        api_key_file = Path(settings.API_KEY_FILE)

        # Try to load existing key
        if api_key_file.exists():
            try:
                api_key = api_key_file.read_text().strip()
                if api_key:
                    logger.info(f"Loaded existing API key from {settings.API_KEY_FILE}")
                    return api_key
            except Exception as e:
                logger.warning(f"Failed to read API key file: {e}. Generating new key.")

        # Generate new cryptographically secure API key (256-bit)
        api_key = secrets.token_urlsafe(32)  # 32 bytes = 256 bits

        # Save with secure permissions (owner read/write only)
        try:
            api_key_file.write_text(api_key)
            # Set file permissions to 0600 (owner read/write only)
            os.chmod(api_key_file, 0o600)
            logger.info(f"Generated new API key and saved to {settings.API_KEY_FILE} with 0600 permissions")
        except Exception as e:
            logger.error(f"Failed to save API key: {e}")
            raise

        return api_key

    async def _agent_loop(self):
        """
        Periodically runs the agent graph.
        """
        logger.info("Starting Agent Graph Loop...")
        while self._running:
            try:
                if self._graph:
                    initial_state = AgentState(
                        command={},
                        action_plan=[],
                        execution_result={},
                        status="idle",
                        messages=[]
                    )
                    # Invoke graph
                    result = await self._graph.ainvoke(initial_state)
                    if result.get("status") != "idle":
                        logger.debug(f"Agent Graph Result: {result.get('status')} - {result.get('messages')}")
            except Exception as e:
                logger.error(f"Error in Agent Graph Loop: {e}")

            await asyncio.sleep(5)  # Run every 5 seconds (more frequent for actions)

    async def _authenticate(self):
        """
        Authenticates with Core to register and get ID.
        Sends the agent's unique API key for storage.
        """
        try:
            logger.info("Authenticating with Core...")
            payload = {
                "agent_type": settings.AGENT_TYPE,
                "agent_subtype": settings.AGENT_SUBTYPE,
                "zone": settings.ZONE,
                "capabilities": settings.CAPABILITIES,
                "metadata": {"hostname": "localhost"},
                "api_key": self._api_key  # Send API key for registration
            }

            timeout = aiohttp.ClientTimeout(total=10)
            async with self._session.post(
                    f"{settings.CORE_API_URL}/agents/register",
                    json=payload,
                    timeout=timeout
            ) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._agent_id = data.get("id")
                    logger.info(f"Successfully registered agent {self._agent_id} with API key")
                else:
                    text = await resp.text()
                    logger.error(f"Failed to register agent: {resp.status} - {text}")
                    raise Exception(f"Agent registration failed: {text}")
        except Exception as e:
            logger.error(f"Error during authentication: {e}")
            raise

    async def _heartbeat_loop(self):
        """
        Sends periodic heartbeats to Core with API key authentication.
        """
        while self._running:
            try:
                if hasattr(self, '_agent_id') and self._agent_id:
                    payload = {
                        "agent_id": self._agent_id,
                        "status": "active",
                        "resource_usage": {}  # Placeholder
                    }
                    # Authenticate with API key header
                    headers = {"X-Agent-API-Key": self._api_key}
                    async with self._session.post(
                            f"{settings.CORE_API_URL}/agents/heartbeat",
                            json=payload,
                            headers=headers
                    ) as resp:
                        if resp.status == 200:
                            logger.debug("Heartbeat sent successfully")
                        else:
                            text = await resp.text()
                            logger.warning(f"Heartbeat failed: {resp.status} - {text}")
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

            await asyncio.sleep(30)
