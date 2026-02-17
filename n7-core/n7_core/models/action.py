
from sqlalchemy import String, JSON, Integer
from sqlalchemy.dialects.postgresql import UUID, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
import uuid

from ..database.base import Base, UUIDMixin, TimestampMixin

class Action(Base, UUIDMixin, TimestampMixin):
    """
    Action Model.
    Ref: TDD Section 9.1.4 Action Data Model
    """
    __tablename__ = "actions"

    action_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4, name="id")
    incident_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)
    striker_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=True, index=True)  # FK to agents table
    action_type: Mapped[str] = mapped_column(String, nullable=False)  # block_ip, kill_process, isolate_host, etc.
    parameters: Mapped[dict] = mapped_column(JSON, default=dict)  # Action-specific parameters
    status: Mapped[str] = mapped_column(String, default="queued")  # queued, executing, succeeded, failed, rolled_back
    initiated_by: Mapped[str] = mapped_column(String, nullable=False)  # "auto" or operator username
    evidence: Mapped[dict] = mapped_column(JSON, default=dict, nullable=True)  # Pre-action forensic captures
    rollback_entry: Mapped[dict] = mapped_column(JSON, nullable=True)  # Rollback instructions

    def __repr__(self):
        return f"<Action(id={self.action_id}, type={self.action_type}, status={self.status})>"
