from datetime import datetime

from sqlalchemy import String, Integer, DateTime
from sqlalchemy.orm import Mapped, mapped_column

from ..database.base import Base, UUIDMixin, TimestampMixin


class InfraNode(Base, UUIDMixin, TimestampMixin):
    """
    Infrastructure Node Registry.
    Represents discovered or manually added hosts that can receive agent deployments.
    """
    __tablename__ = "infra_nodes"

    hostname: Mapped[str] = mapped_column(String, nullable=True)
    ip_address: Mapped[str] = mapped_column(String, nullable=False, index=True, unique=True)
    os_type: Mapped[str] = mapped_column(String, nullable=True)  # linux, macos, windows, unknown
    ssh_port: Mapped[int] = mapped_column(Integer, default=22)
    winrm_port: Mapped[int] = mapped_column(Integer, default=5985)
    mac_address: Mapped[str] = mapped_column(String, nullable=True)  # e.g. aa:bb:cc:dd:ee:ff
    ssh_username: Mapped[str] = mapped_column(String, nullable=True)
    ssh_password_enc: Mapped[str] = mapped_column(String, nullable=True)  # Fernet-encrypted
    ssh_key_path: Mapped[str] = mapped_column(String, nullable=True)  # path on Core host
    # status: discovered | reachable | unreachable | deployed | failed
    status: Mapped[str] = mapped_column(String, default="discovered")
    # deployment_status: none | pending | in_progress | success | failed
    deployment_status: Mapped[str] = mapped_column(String, default="none")
    deployed_agent_type: Mapped[str] = mapped_column(String, nullable=True)  # sentinel | striker
    deployed_agent_id: Mapped[str] = mapped_column(String, nullable=True)    # soft ref to agents.id
    last_seen: Mapped[datetime] = mapped_column(DateTime, nullable=True)
    discovery_method: Mapped[str] = mapped_column(String, default="manual")  # nmap | ping | manual
    error_message: Mapped[str] = mapped_column(String, nullable=True)
