import asyncio
import json
import logging
import os
import secrets
from pathlib import Path

import aiohttp

from .config import settings
from .graph import build_striker_graph, AgentState
from ..agent_id import load_persisted_agent_id, set_agent_id
from ..config_loader import fetch_remote_config

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
        self._nats_client = None
        self._config_version: int = 0

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

        # Connect to NATS for push-based heartbeats
        await self._connect_nats()

        # Build Graph
        self._graph = build_striker_graph()

        # Start Heartbeat Loop
        asyncio.create_task(self._heartbeat_loop())
        # Start Agent Graph Loop
        asyncio.create_task(self._agent_loop())
        # Start Config Poll Loop (checks for config version changes every 60s)
        asyncio.create_task(self._config_poll_loop())

    async def stop(self):
        self._running = False
        if self._nats_client:
            try:
                await self._nats_client.nc.close()
            except Exception:
                pass
        if self._session:
            await self._session.close()
        logger.info("AgentRuntimeService stopped.")

    async def _connect_nats(self):
        """Connect to NATS for push-based heartbeats and config-push subscription. Fails gracefully if unavailable."""
        if not settings.NATS_URL:
            logger.warning("NATS_URL not set — NATS heartbeats disabled, using HTTP fallback.")
            return
        try:
            from ..messaging.nats_client import nats_client as _nc
            self._nats_client = _nc
            await self._nats_client.connect()
            logger.info(f"Connected to NATS at {settings.NATS_URL}")
            # Subscribe to config-push subject so Core can update us immediately
            await self._subscribe_config_push()
        except Exception as e:
            logger.warning(f"NATS connection failed: {e} — heartbeats will use HTTP fallback.")
            self._nats_client = None

    async def _subscribe_config_push(self):
        """
        Subscribe to n7.config.<agent_id> for real-time config updates pushed by Core.
        When Core saves a new config version it publishes the full config snapshot to
        this subject so the agent applies it immediately without waiting for the 60s poll.
        """
        if not self._agent_id or not self._nats_client:
            return
        subject = f"n7.config.{self._agent_id}"

        async def _on_config_push(msg):
            try:
                data = json.loads(msg.data.decode())
                incoming_version = data.get("config_version", 0)
                if incoming_version <= self._config_version:
                    logger.debug(
                        f"Config push ignored: incoming version {incoming_version} "
                        f"<= current {self._config_version}"
                    )
                    return
                logger.info(
                    f"Config push received: version {self._config_version} → {incoming_version}. "
                    "Applying immediately."
                )
                # Apply the pushed fields directly into settings
                if data.get("zone"):
                    settings.ZONE = data["zone"]
                if data.get("log_level"):
                    settings.LOG_LEVEL = data["log_level"]
                    logging.getLogger().setLevel(data["log_level"])
                if data.get("capabilities"):
                    settings.CAPABILITIES = data["capabilities"]
                if "allowed_actions" in data:
                    settings.ALLOWED_ACTIONS = data["allowed_actions"]
                if data.get("action_defaults"):
                    settings.ACTION_DEFAULTS = data["action_defaults"]
                if "max_concurrent_actions" in data:
                    settings.MAX_CONCURRENT_ACTIONS = data["max_concurrent_actions"]
                self._config_version = incoming_version
                logger.info(
                    f"Applied pushed config v{incoming_version}: "
                    f"capabilities={settings.CAPABILITIES}, "
                    f"allowed_actions={settings.ALLOWED_ACTIONS}"
                )
            except Exception as e:
                logger.error(f"Failed to process config push: {e}")

        await self._nats_client.nc.subscribe(subject, cb=_on_config_push)
        logger.info(f"Subscribed to config push on {subject}")

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
        # Striker-specific
        if remote.get("capabilities"):
            settings.CAPABILITIES = remote["capabilities"]
        if "allowed_actions" in remote:
            settings.ALLOWED_ACTIONS = remote["allowed_actions"]
        if remote.get("action_defaults"):
            settings.ACTION_DEFAULTS = remote["action_defaults"]
        if "max_concurrent_actions" in remote:
            settings.MAX_CONCURRENT_ACTIONS = remote["max_concurrent_actions"]

        new_version = remote.get("config_version", 0)
        self._config_version = new_version

        logger.info(
            f"Applied remote config version {new_version} "
            f"(zone={settings.ZONE}, capabilities={settings.CAPABILITIES}, "
            f"allowed_actions={settings.ALLOWED_ACTIONS})"
        )

    async def _config_poll_loop(self):
        """
        Periodically checks if config_version has changed on Core.
        Re-applies config when a newer version is detected.
        Runs every 60 seconds.
        """
        while self._running:
            await asyncio.sleep(60)
            if not self._agent_id:
                continue
            try:
                remote = await fetch_remote_config(
                    core_api_url=settings.CORE_API_URL,
                    agent_id=self._agent_id,
                    api_key=self._api_key,
                    session=self._session,
                )
                if remote and remote.get("config_version", 0) > self._config_version:
                    logger.info(
                        f"Config version changed: {self._config_version} → "
                        f"{remote.get('config_version')}. Re-applying config."
                    )
                    await self._apply_remote_config()
            except Exception as e:
                logger.debug(f"Config poll error (non-fatal): {e}")

    async def _authenticate(self):
        """
        Authenticates with Core to register and get ID.
        Retries with exponential backoff until Core is reachable.
        """
        payload = {
            "agent_type": settings.AGENT_TYPE,
            "agent_subtype": settings.AGENT_SUBTYPE,
            "zone": settings.ZONE,
            "capabilities": settings.CAPABILITIES,
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
                        
                        client_cert = data.get("client_cert")
                        client_key = data.get("client_key")
                        ca_cert = data.get("ca_cert")
                        if client_cert and client_key:
                            certs_dir = Path("agent_certs")
                            certs_dir.mkdir(exist_ok=True)
                            cert_path = certs_dir / "client.crt"
                            key_path = certs_dir / "client.key"
                            cert_path.write_text(client_cert)
                            key_path.write_text(client_key)
                            os.chmod(key_path, 0o600)
                            if ca_cert:
                                (certs_dir / "ca.crt").write_text(ca_cert)
                            
                            logger.info("Saved mTLS certificates from Core.")
                            # Switch session to use mTLS
                            import ssl
                            ssl_context = ssl.create_default_context()
                            ssl_context.check_hostname = False
                            ssl_context.verify_mode = ssl.CERT_NONE
                            ssl_context.load_cert_chain(certfile=str(cert_path), keyfile=str(key_path))
                            
                            connector = aiohttp.TCPConnector(ssl=ssl_context)
                            await self._session.close()
                            self._session = aiohttp.ClientSession(connector=connector)
                            
                            # Update API URL to point to mTLS port
                            if "8000" in settings.CORE_API_URL:
                                settings.CORE_API_URL = settings.CORE_API_URL.replace("http://", "https://").replace("8000", "8443")
                                logger.info(f"Switched HTTP session to mTLS at {settings.CORE_API_URL}")

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
        Sends periodic heartbeats to Core.
        Prefers NATS publish (push-based, low overhead at scale).
        Falls back to HTTP POST if NATS is not connected.

        NATS topic: n7.heartbeat.striker.{agent_id}
        HTTP fallback: POST /agents/heartbeat (kept for graceful degradation)
        """
        while self._running:
            try:
                if self._agent_id:
                    payload = {
                        "agent_id": self._agent_id,
                        "agent_type": settings.AGENT_TYPE,
                        "agent_subtype": settings.AGENT_SUBTYPE,
                        "zone": settings.ZONE,
                        "status": "active",
                        "resource_usage": {}  # Placeholder
                    }

                    if self._nats_client and self._nats_client.nc.is_connected:
                        # Push-based via NATS — preferred path (scales to 400+ nodes)
                        subject = f"n7.heartbeat.striker.{self._agent_id}"
                        await self._nats_client.nc.publish(
                            subject,
                            json.dumps(payload).encode()
                        )
                        logger.debug(f"Heartbeat published to NATS: {subject}")
                    else:
                        # HTTP fallback
                        headers = {"X-Agent-API-Key": self._api_key}
                        async with self._session.post(
                                f"{settings.CORE_API_URL}/agents/heartbeat",
                                json=payload,
                                headers=headers
                        ) as resp:
                            if resp.status == 200:
                                logger.debug("Heartbeat sent via HTTP fallback")
                            elif resp.status == 404:
                                logger.warning("Heartbeat 404: agent not found on Core, re-registering...")
                                self._agent_id = None
                                await self._authenticate()
                            elif resp.status == 403:
                                logger.warning("Heartbeat 403: agent ID mismatch, re-registering to sync...")
                                self._agent_id = None
                                await self._authenticate()
                            else:
                                text = await resp.text()
                                logger.warning(f"Heartbeat failed: {resp.status} - {text}")
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")

            await asyncio.sleep(30)
