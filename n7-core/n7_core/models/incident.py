from sqlalchemy import String, JSON
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base, UUIDMixin, TimestampMixin


class Incident(Base, UUIDMixin, TimestampMixin):
    """
    Incident Model.
    Ref: TDD Section 9.1.3 Incident Data Model
    """
    __tablename__ = "incidents"

    alert_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="open")  # open, contained, eradicated, recovered, closed
    assigned_to: Mapped[str] = mapped_column(String, nullable=True)
    playbook_id: Mapped[str] = mapped_column(String, nullable=True)  # ID of playbook used for response
    actions: Mapped[list] = mapped_column(JSON, default=list)  # List of action summaries
    timeline: Mapped[list] = mapped_column(JSON, default=list)  # Chronological event/action log
