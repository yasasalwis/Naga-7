from sqlalchemy import String, JSON, ARRAY
from sqlalchemy.orm import Mapped, mapped_column
from ..database.base import Base, UUIDMixin, TimestampMixin

class Incident(Base, UUIDMixin, TimestampMixin):
    """
    Incident Model.
    Ref: TDD Section 4.5 Data Architecture
    """
    __tablename__ = "incidents"

    alert_ids: Mapped[list[str]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String, default="open") # open, contained, closed
    assigned_to: Mapped[str] = mapped_column(String, nullable=True)
    actions: Mapped[list] = mapped_column(JSON, default=list) # List of action summaries
    timeline: Mapped[list] = mapped_column(JSON, default=list) # Audit trail of this incident
