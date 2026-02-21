import asyncio
import logging
import os
import secrets
from pathlib import Path

import aiohttp

from .config import settings
from .graph import build_sentinel_graph, AgentState
from ..agent_id import load_persisted_agent_id, set_agent_id
from ..config_loader import fetch_remote_config

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
        self._api_key = None  # Agent's unique API key
        self._agent_id = None
        self._graph = None

        # Load or generate API key on initialization
        self._api_key = self._load_or_generate_api_key()

        # Attempt to restore a previously Core-assigned agent ID from disk
        self._agent_id = load_persisted_agent_id()

    async def start(self):
        self._running = True
        logger.info("AgentRuntimeService started.")
        self._session = aiohttp.ClientSession()

        # Authenticate with Core
        await self._authenticate()

        # Pull centralized config from Core DB and apply it
        await self._apply_remote_config()

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

            await asyncio.sleep(10)  # Run every 10 seconds

    async def _apply_remote_config(self):
        """
        Pull centralized config from Core DB and override in-memory settings values.
        Gracefully degrades — on any failure the agent continues with its bootstrap .env.
        """
        if not self._agent_id:
            logger.warning("Cannot fetch remote config: agent_id not yet assigned.")
            return

        remote = await fetch_remote_config(
            core_api_url=settings.CORE_API_URL,
            agent_id=self._agent_id,
            api_key=self._api_key,
            session=self._session,
        )
        if remote is None:
            logger.info("Continuing with bootstrap .env configuration.")
            return

        # Apply decrypted values to live settings
        if remote.get("nats_url"):
            settings.NATS_URL = remote["nats_url"]
        if remote.get("core_api_url"):
            settings.CORE_API_URL = remote["core_api_url"]
        if remote.get("log_level"):
            settings.LOG_LEVEL = remote["log_level"]
            logging.getLogger().setLevel(remote["log_level"])
        if remote.get("zone"):
            settings.ZONE = remote["zone"]

        logger.info(
            f"Applied remote config version {remote.get('config_version', '?')} "
            f"(zone={settings.ZONE}, nats={settings.NATS_URL})"
        )

    async def _authenticate(self):
        """
        Authenticates with Core to register and get ID.
        Retries with exponential backoff until Core is reachable.
        """
        payload = {
            "agent_type": settings.AGENT_TYPE,
            "agent_subtype": settings.AGENT_SUBTYPE,
            "zone": settings.ZONE,
            "capabilities": ["system_probe", "file_integrity"],  # Dynamic in real world
            "metadata": {"hostname": "localhost"},
            "api_key": self._api_key
        }
        timeout = aiohttp.ClientTimeout(total=10)
        delay = 2
        attempt = 0
        while self._running:
            attempt += 1
            try:
                logger.info(f"Authenticating with Core (attempt {attempt})...")
                async with self._session.post(
                        f"{settings.CORE_API_URL}/agents/register",
                        json=payload,
                        timeout=timeout
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self._agent_id = data.get("id")
                        set_agent_id(self._agent_id)
                        logger.info(f"Successfully registered agent {self._agent_id}")
                        return
                    else:
                        text = await resp.text()
                        logger.error(f"Registration rejected by Core: {resp.status} - {text}")
                        raise Exception(f"Agent registration failed: {text}")
            except aiohttp.ClientConnectorError as e:
                logger.warning(f"Core not reachable (attempt {attempt}): {e}. Retrying in {delay}s...")
            except Exception as e:
                logger.error(f"Authentication error (attempt {attempt}): {e}. Retrying in {delay}s...")
            await asyncio.sleep(delay)
            delay = min(delay * 2, 60)  # cap at 60 s

    async def _heartbeat_loop(self):
        """
        Sends periodic heartbeats to Core with API key authentication.
        On 404 the agent record is gone from Core (e.g. DB wipe); re-register.
        """
        while self._running:
            try:
                if hasattr(self, '_agent_id') and self._agent_id:
                    payload = {
                        "agent_id": self._agent_id,
                        "status": "active",
                        "resource_usage": {"cpu": 10, "memory": 20}  # Placeholder
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
                        elif resp.status == 404:
                            # Agent record missing on Core — re-register
                            logger.warning("Heartbeat 404: agent not found on Core, re-registering...")
                            self._agent_id = None
                            await self._authenticate()
                        else:
                            text = await resp.text()
                            logger.warning(f"Heartbeat failed: {resp.status} - {text}")
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

            await asyncio.sleep(30)
