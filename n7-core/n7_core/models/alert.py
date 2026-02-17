from sqlalchemy import String, JSON, Integer
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base, UUIDMixin, TimestampMixin


class Alert(Base, UUIDMixin, TimestampMixin):
    """
    Alert Model.
    Ref: TDD Section 4.5 Data Architecture
    """
    __tablename__ = "alerts"

    # We store event_ids as a JSON array or PostgreSQL array. 
    # Using JSON for broader compatibility, but ARRAY(UUID) is better for Postgres.
    # Given we are strict on Postgres, let's use ARRAY(String) to avoid UUID complications in lists for now.
    event_ids: Mapped[list[str]] = mapped_column(JSON, default=list)

    threat_score: Mapped[int] = mapped_column(Integer, default=0)
    severity: Mapped[str] = mapped_column(String, nullable=False)  # low, medium, high, critical
    status: Mapped[str] = mapped_column(String, default="new")  # new, acknowledged, resolved
    verdict: Mapped[str] = mapped_column(String, nullable=True)  # auto_respond, escalate
    affected_assets: Mapped[list] = mapped_column(JSON, default=list)
    reasoning: Mapped[dict] = mapped_column(JSON, default=dict)
