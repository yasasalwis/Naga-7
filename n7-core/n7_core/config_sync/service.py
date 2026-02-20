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
        nats_url: str,
        core_api_url: str,
        zone: str = "default",
        log_level: str = "INFO",
        environment: str = "production",
        probe_interval_seconds: int = 5,
        capabilities: Optional[list] = None,
        detection_thresholds: Optional[dict] = None,
    ) -> AgentConfig:
        """
        Create or replace the config entry for a newly deployed agent.
        Called by DeploymentService immediately after a successful SSH/WinRM deploy.
        Sensitive fields are encrypted with Core's SECRET_KEY before storage.
        """
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
                cfg.probe_interval_seconds = probe_interval_seconds
                if capabilities is not None:
                    cfg.capabilities = capabilities
                if detection_thresholds is not None:
                    cfg.detection_thresholds = detection_thresholds
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
                    probe_interval_seconds=probe_interval_seconds,
                    capabilities=capabilities or [],
                    detection_thresholds=detection_thresholds or {},
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
            "probe_interval_seconds": cfg.probe_interval_seconds,
            "detection_thresholds": cfg.detection_thresholds or {},
            "capabilities": cfg.capabilities or [],
            "config_version": cfg.config_version,
        }

    async def upsert_config(self, agent_id: UUID, config_dict: dict) -> AgentConfig:
        """
        Update specific config fields for an agent. Sensitive fields in config_dict
        should be passed as plaintext — they will be encrypted before storage.
        Increments config_version on each call.
        """
        async with async_session_maker() as session:
            result = await session.execute(
                select(AgentConfig).where(AgentConfig.agent_id == agent_id)
            )
            cfg = result.scalar_one_or_none()
            if not cfg:
                raise ValueError(f"No config found for agent {agent_id}. Call provision_agent_config first.")

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
            if "probe_interval_seconds" in config_dict:
                cfg.probe_interval_seconds = config_dict["probe_interval_seconds"]
            if "detection_thresholds" in config_dict:
                cfg.detection_thresholds = config_dict["detection_thresholds"]
            if "capabilities" in config_dict:
                cfg.capabilities = config_dict["capabilities"]

            cfg.config_version += 1
            cfg.updated_at = datetime.utcnow()
            await session.commit()
            await session.refresh(cfg)
            logger.info(f"Updated config for agent {agent_id} (version {cfg.config_version})")
            return cfg
