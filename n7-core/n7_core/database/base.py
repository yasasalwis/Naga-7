
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from sqlalchemy.ext.asyncio import AsyncAttrs
from datetime import datetime
from uuid import UUID, uuid4
from sqlalchemy import DateTime

class Base(AsyncAttrs, DeclarativeBase):
    """
    Base class for all ORM models.
    Includes common fields like id, created_at, updated_at.
    """
    pass

class TimestampMixin:
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

class UUIDMixin:
    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
