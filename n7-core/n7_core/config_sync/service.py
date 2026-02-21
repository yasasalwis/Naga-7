import base64
import hashlib
import logging
from datetime import datetime
from typing import Optional
from uuid import UUID

from cryptography.fernet import Fernet
from sqlalchemy import select

from ..config import settings
from ..database.session import async_session_maker
from ..models.agent_config import AgentConfig
from ..service_manager.base_service import BaseService

logger = logging.getLogger("n7-core.config-sync")


def _derive_fernet_key(secret: str) -> bytes:
    """Derive a 32-byte URL-safe base64 Fernet key from an arbitrary secret string."""
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


class ConfigSyncService(BaseService):
    """
    Config Sync Service.
    Responsibility: Manage centralized, versioned per-agent configuration stored in DB.

    Sensitive fields (nats_url, core_api_url) are Fernet-encrypted at rest using the
    Core's SECRET_KEY. When serving config to an agent via the API, those fields are
    additionally re-encrypted with a key derived from that agent's own API key —
    so only the requesting agent can decrypt them.

    Ref: TDD Section 5.x Agent Configuration Management
    """

    def __init__(self):
        super().__init__("ConfigSyncService")
        self._fernet = Fernet(_derive_fernet_key(settings.SECRET_KEY))

    async def start(self):
        logger.info("ConfigSyncService started.")

    async def stop(self):
        logger.info("ConfigSyncService stopped.")

    # ------------------------------------------------------------------
    # Storage-level encryption (Core SECRET_KEY)
    # ------------------------------------------------------------------

    def _encrypt_for_storage(self, plain: str) -> str:
        return self._fernet.encrypt(plain.encode()).decode()

    def _decrypt_from_storage(self, enc: str) -> str:
        return self._fernet.decrypt(enc.encode()).decode()

    # ------------------------------------------------------------------
    # Transport-level encryption (agent API key)
    # Used so only the target agent can decrypt nats_url / core_api_url
    # ------------------------------------------------------------------

    @staticmethod
    def _agent_fernet(api_key: str) -> Fernet:
        """Derive a Fernet instance keyed to a specific agent's API key."""
        return Fernet(_derive_fernet_key(api_key))

    def _encrypt_for_transport(self, plain: str, api_key: str) -> str:
        return self._agent_fernet(api_key).encrypt(plain.encode()).decode()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def provision_agent_config(
        self,
        agent_id: UUID,
        agent_type: str,
        nats_url: str,
        core_api_url: str,
        zone: str = "default",
        log_level: str = "INFO",
        environment: str = "production",
        # Sentinel-specific
        probe_interval_seconds: int = 10,
        detection_thresholds: Optional[dict] = None,
        enabled_probes: Optional[list] = None,
        # Striker-specific
        capabilities: Optional[list] = None,
        allowed_actions: Optional[list] = None,
        action_defaults: Optional[dict] = None,
        max_concurrent_actions: Optional[int] = None,
    ) -> AgentConfig:
        """
        Create or replace the config entry for a newly deployed agent.
        Called by DeploymentService immediately after a successful SSH/WinRM deploy.
        Sensitive fields are encrypted with Core's SECRET_KEY before storage.
        agent_type must be "sentinel" or "striker" — used to set type-appropriate defaults.
        """
        # Sentinel defaults
        if agent_type == "sentinel":
            detection_thresholds = detection_thresholds or {
                "cpu_threshold": 80,
                "mem_threshold": 85,
                "disk_threshold": 90,
                "load_multiplier": 2.0,
            }
            enabled_probes = enabled_probes or ["system", "network", "process", "file"]

        # Striker defaults
        if agent_type == "striker":
            capabilities = capabilities or ["network_block", "process_kill", "file_quarantine"]
            action_defaults = action_defaults or {"network_block": {"duration": 3600}}

        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentConfig).where(AgentConfig.agent_id == agent_id)
            )
            cfg = result.scalar_one_or_none()

            encrypted_nats = self._encrypt_for_storage(nats_url)
            encrypted_core = self._encrypt_for_storage(core_api_url)

            if cfg:
                cfg.nats_url_enc = encrypted_nats
                cfg.core_api_url_enc = encrypted_core
                cfg.zone = zone
                cfg.log_level = log_level
                cfg.environment = environment
                # Sentinel fields
                cfg.probe_interval_seconds = probe_interval_seconds
                if detection_thresholds is not None:
                    cfg.detection_thresholds = detection_thresholds
                if enabled_probes is not None:
                    cfg.enabled_probes = enabled_probes
                # Striker fields
                if capabilities is not None:
                    cfg.capabilities = capabilities
                if allowed_actions is not None:
                    cfg.allowed_actions = allowed_actions
                if action_defaults is not None:
                    cfg.action_defaults = action_defaults
                if max_concurrent_actions is not None:
                    cfg.max_concurrent_actions = max_concurrent_actions
                cfg.config_version += 1
                cfg.updated_at = datetime.utcnow()
            else:
                cfg = AgentConfig(
                    agent_id=agent_id,
                    nats_url_enc=encrypted_nats,
                    core_api_url_enc=encrypted_core,
                    zone=zone,
                    log_level=log_level,
                    environment=environment,
                    # Sentinel fields
                    probe_interval_seconds=probe_interval_seconds,
                    detection_thresholds=detection_thresholds,
                    enabled_probes=enabled_probes,
                    # Striker fields
                    capabilities=capabilities,
                    allowed_actions=allowed_actions,
                    action_defaults=action_defaults,
                    max_concurrent_actions=max_concurrent_actions,
                    config_version=1,
                    updated_at=datetime.utcnow(),
                )
                session.add(cfg)

            await session.commit()
            await session.refresh(cfg)
            logger.info(f"Provisioned config for agent {agent_id} (version {cfg.config_version})")
            return cfg

    async def get_config_for_agent(self, agent_id: UUID, api_key: str) -> Optional[dict]:
        """
        Fetch the config for an agent and return it as a dict ready for the API response.

        Sensitive fields (nats_url, core_api_url) are:
        1. Decrypted from storage (Core key)
        2. Re-encrypted for transport (agent's API key)

        The agent derives the same transport key from its own API key to decrypt locally.
        All other fields are returned in plaintext.

        Returns None if no config exists for this agent.
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentConfig).where(AgentConfig.agent_id == agent_id)
            )
            cfg = result.scalar_one_or_none()
            if not cfg:
                return None

        try:
            plain_nats = self._decrypt_from_storage(cfg.nats_url_enc) if cfg.nats_url_enc else None
            plain_core = self._decrypt_from_storage(cfg.core_api_url_enc) if cfg.core_api_url_enc else None
        except Exception as e:
            logger.error(f"Failed to decrypt config for agent {agent_id}: {e}")
            return None

        # Re-encrypt with agent's key for transport
        transport_nats = self._encrypt_for_transport(plain_nats, api_key) if plain_nats else None
        transport_core = self._encrypt_for_transport(plain_core, api_key) if plain_core else None

        return {
            "agent_id": str(agent_id),
            "nats_url_enc": transport_nats,
            "core_api_url_enc": transport_core,
            "log_level": cfg.log_level,
            "environment": cfg.environment,
            "zone": cfg.zone,
            "config_version": cfg.config_version,
            # Sentinel-specific
            "probe_interval_seconds": cfg.probe_interval_seconds,
            "detection_thresholds": cfg.detection_thresholds or {},
            "enabled_probes": cfg.enabled_probes or [],
            # Striker-specific
            "capabilities": cfg.capabilities or [],
            "allowed_actions": cfg.allowed_actions,
            "action_defaults": cfg.action_defaults or {},
            "max_concurrent_actions": cfg.max_concurrent_actions,
        }

    async def upsert_config(self, agent_id: UUID, config_dict: dict, agent_type: str = "") -> AgentConfig:
        """
        Update specific config fields for an agent. Sensitive fields in config_dict
        should be passed as plaintext — they will be encrypted before storage.
        Increments config_version on each call. Creates a default config row if none exists.
        agent_type is used only when auto-provisioning a new row (sets type-appropriate defaults).
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentConfig).where(AgentConfig.agent_id == agent_id)
            )
            cfg = result.scalar_one_or_none()
            if not cfg:
                # Auto-provision a default config row so operators can configure
                # agents that registered themselves (not deployed via DeploymentService).
                from ..config import settings as _settings
                encrypted_nats = self._encrypt_for_storage(_settings.NATS_URL)
                encrypted_core = self._encrypt_for_storage(
                    f"http://{_settings.API_HOST}:{_settings.API_PORT}"
                )
                # Set type-appropriate defaults
                sentinel_thresholds = None
                sentinel_probes = None
                striker_caps = None
                striker_defaults = None
                if agent_type == "sentinel":
                    sentinel_thresholds = {
                        "cpu_threshold": 80,
                        "mem_threshold": 85,
                        "disk_threshold": 90,
                        "load_multiplier": 2.0,
                    }
                    sentinel_probes = ["system", "network", "process", "file"]
                elif agent_type == "striker":
                    striker_caps = ["network_block", "process_kill", "file_quarantine"]
                    striker_defaults = {"network_block": {"duration": 3600}}

                cfg = AgentConfig(
                    agent_id=agent_id,
                    nats_url_enc=encrypted_nats,
                    core_api_url_enc=encrypted_core,
                    zone="default",
                    log_level="INFO",
                    environment=_settings.ENVIRONMENT,
                    # Sentinel fields
                    probe_interval_seconds=10,
                    detection_thresholds=sentinel_thresholds,
                    enabled_probes=sentinel_probes,
                    # Striker fields
                    capabilities=striker_caps,
                    allowed_actions=None,
                    action_defaults=striker_defaults,
                    max_concurrent_actions=None,
                    config_version=0,
                    updated_at=datetime.utcnow(),
                )
                session.add(cfg)
                logger.info(f"Auto-provisioned default config for agent {agent_id} (type={agent_type or 'unknown'})")

            # Shared fields
            if "nats_url" in config_dict:
                cfg.nats_url_enc = self._encrypt_for_storage(config_dict["nats_url"])
            if "core_api_url" in config_dict:
                cfg.core_api_url_enc = self._encrypt_for_storage(config_dict["core_api_url"])
            if "log_level" in config_dict:
                cfg.log_level = config_dict["log_level"]
            if "environment" in config_dict:
                cfg.environment = config_dict["environment"]
            if "zone" in config_dict:
                cfg.zone = config_dict["zone"]
            # Sentinel-specific fields
            if "probe_interval_seconds" in config_dict:
                cfg.probe_interval_seconds = config_dict["probe_interval_seconds"]
            if "detection_thresholds" in config_dict:
                cfg.detection_thresholds = config_dict["detection_thresholds"]
            if "enabled_probes" in config_dict:
                cfg.enabled_probes = config_dict["enabled_probes"]
            # Striker-specific fields
            if "capabilities" in config_dict:
                cfg.capabilities = config_dict["capabilities"]
            if "allowed_actions" in config_dict:
                cfg.allowed_actions = config_dict["allowed_actions"]
            if "action_defaults" in config_dict:
                cfg.action_defaults = config_dict["action_defaults"]
            if "max_concurrent_actions" in config_dict:
                cfg.max_concurrent_actions = config_dict["max_concurrent_actions"]

            cfg.config_version += 1
            cfg.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(cfg)
            logger.info(f"Updated config for agent {agent_id} (version {cfg.config_version})")
            return cfg
