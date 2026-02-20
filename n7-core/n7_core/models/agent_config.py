from datetime import datetime
from typing import Optional
from uuid import UUID

from sqlalchemy import DateTime, Integer, String, JSON
from sqlalchemy.dialects.postgresql import UUID as PGUUID
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base, UUIDMixin


class AgentConfig(Base, UUIDMixin):
    """
    Per-agent configuration store.
    Allows Core to centrally manage and push config to deployed Sentinels and Strikers,
    replacing static .env files with DB-backed, versioned, encrypted config.

    Sensitive fields (nats_url, core_api_url) are Fernet-encrypted at rest using
    the Core's SECRET_KEY. On the transport layer they are additionally encrypted
    with a key derived from the individual agent's API key so only that agent can
    decrypt them.

    Ref: TDD Section 5.x Agent Configuration Management
    """
    __tablename__ = "agent_configs"

    agent_id: Mapped[UUID] = mapped_column(PGUUID(as_uuid=True), nullable=False, unique=True, index=True)

    # --- Connectivity (stored Fernet-encrypted) ---
    nats_url_enc: Mapped[Optional[str]] = mapped_column(String, nullable=True)
    core_api_url_enc: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # --- Behaviour tunables (plaintext) ---
    log_level: Mapped[Optional[str]] = mapped_column(String, nullable=True)      # DEBUG, INFO, WARNING
    environment: Mapped[Optional[str]] = mapped_column(String, nullable=True)    # development, production
    zone: Mapped[Optional[str]] = mapped_column(String, nullable=True)

    # --- Thresholds (plaintext JSON) ---
    detection_thresholds: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # e.g. {"cpu_threshold": 90, "auth_failure_threshold": 5, "probe_interval_seconds": 5}
    probe_interval_seconds: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- Capabilities (plaintext JSON list) ---
    capabilities: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # --- Version tracking ---
    config_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        onupdate=datetime.utcnow,
        nullable=False,
    )

    def __repr__(self):
        return f"<AgentConfig(agent_id={self.agent_id}, version={self.config_version})>"
