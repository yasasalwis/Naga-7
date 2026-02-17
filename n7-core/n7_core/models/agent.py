from datetime import datetime

from sqlalchemy import String, JSON, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base, UUIDMixin, TimestampMixin


class Agent(Base, UUIDMixin, TimestampMixin):
    """
    Agent Registry Model.
    Ref: TDD Section 4.5 Agent Registry Data Model
    """
    __tablename__ = "agents"

    agent_type: Mapped[str] = mapped_column(String, nullable=False)  # sentinel, striker
    agent_subtype: Mapped[str] = mapped_column(String, nullable=False)  # network, endpoint, etc.
    status: Mapped[str] = mapped_column(String, default="active")  # active, unhealthy, etc.
    capabilities: Mapped[list] = mapped_column(JSON, default=list)
    zone: Mapped[str] = mapped_column(String, default="default")
    last_heartbeat: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)
    config_version: Mapped[int] = mapped_column(Integer, default=1)
    resource_usage: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_: Mapped[dict] = mapped_column(JSON, default=dict, name="metadata")  # metadata is reserved in SQLAlchemy
    api_key_prefix: Mapped[str] = mapped_column(String(16), nullable=False,
                                                index=True)  # First 16 chars for O(1) lookup
    api_key_hash: Mapped[str] = mapped_column(String, nullable=False, unique=True, index=True)
