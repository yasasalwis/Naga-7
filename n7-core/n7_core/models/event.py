
from sqlalchemy import String, JSON, DateTime
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import Mapped, mapped_column
from datetime import datetime
import uuid

from ..database.base import Base

class Event(Base):
    __tablename__ = "events"

    event_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    timestamp: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False, index=True)
    sentinel_id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), nullable=False, index=True)
    event_class: Mapped[str] = mapped_column(String, nullable=False, index=True) # network, endpoint, cloud, application
    severity: Mapped[str] = mapped_column(String, nullable=False) # informational, low, medium, high, critical
    raw_data: Mapped[dict] = mapped_column(JSON, nullable=False)
    enrichments: Mapped[dict] = mapped_column(JSON, default=dict)
    mitre_techniques: Mapped[list] = mapped_column(JSON, default=list)

    def __repr__(self):
        return f"<Event(id={self.event_id}, sentinel={self.sentinel_id}, class={self.event_class})>"
