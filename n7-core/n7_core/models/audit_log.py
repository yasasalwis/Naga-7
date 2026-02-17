
from sqlalchemy import String, JSON, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
import uuid
import hashlib

from ..database.base import Base

class AuditLog(Base):
    """
    Audit Log Model with Hash Chain for Tamper Detection.
    Ref: SRS FR-C040, FR-C041, FR-C042
    """
    __tablename__ = "audit_log"

    log_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    actor: Mapped[str] = mapped_column(String, nullable=False)  # username or agent_id
    action: Mapped[str] = mapped_column(String, nullable=False, index=True)  # event type (e.g., "event_created", "alert_generated")
    resource: Mapped[str] = mapped_column(String, nullable=True)  # affected resource (e.g., event_id, alert_id)
    details: Mapped[dict] = mapped_column(JSON, default=dict)  # additional context
    previous_hash: Mapped[str] = mapped_column(String(64), nullable=True)  # SHA-256 hash of previous entry
    current_hash: Mapped[str] = mapped_column(String(64), nullable=False)  # SHA-256 hash of this entry

    def __repr__(self):
        return f"<AuditLog(id={self.log_id}, actor={self.actor}, action={self.action})>"

    @staticmethod
    def calculate_hash(log_id: str, timestamp: str, actor: str, action: str, resource: str, details: str, previous_hash: str) -> str:
        """
        Calculate SHA-256 hash for hash chain integrity.
        """
        data = f"{log_id}{timestamp}{actor}{action}{resource}{details}{previous_hash or ''}"
        return hashlib.sha256(data.encode()).hexdigest()
