from datetime import datetime
from typing import Optional, Literal
from uuid import UUID

from pydantic import BaseModel, Field


# --- Request Schemas ---

class ScanRequest(BaseModel):
    network_cidr: str = Field(..., description="CIDR range to scan, e.g. '192.168.1.0/24'")
    method: Literal["nmap", "ping"] = "ping"
    timeout_seconds: int = Field(default=30, ge=5, le=300)


class InfraNodeCreate(BaseModel):
    ip_address: str
    hostname: Optional[str] = None
    mac_address: Optional[str] = None
    os_type: Optional[Literal["linux", "macos", "windows", "unknown"]] = "unknown"
    ssh_port: int = 22
    winrm_port: int = 5985
    ssh_username: Optional[str] = None
    ssh_password: Optional[str] = None   # received plain-text, encrypted before DB storage
    ssh_key_path: Optional[str] = None


class DeployRequest(BaseModel):
    agent_type: Literal["sentinel", "striker"]
    agent_subtype: str = "system"
    zone: str = "default"
    core_api_url: str = Field(
        default="http://localhost:8000/api",
        description="URL the deployed agent will use to reach Core"
    )
    nats_url: str = Field(default="nats://localhost:4222")
    # Credential override at deploy time (if not already stored on the node)
    ssh_username: Optional[str] = None
    ssh_password: Optional[str] = None
    ssh_key_path: Optional[str] = None


# --- Response Schemas ---

class InfraNode(BaseModel):
    """Response schema — never exposes raw credential fields."""
    id: UUID
    hostname: Optional[str]
    ip_address: str
    mac_address: Optional[str]
    os_type: Optional[str]
    ssh_port: int
    winrm_port: int
    ssh_username: Optional[str]
    status: str
    deployment_status: str
    deployed_agent_type: Optional[str]
    deployed_agent_id: Optional[str]
    last_seen: Optional[datetime]
    discovery_method: str
    error_message: Optional[str]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True


class ScanResult(BaseModel):
    discovered: int
    nodes: list[InfraNode]


class DeployResponse(BaseModel):
    node_id: UUID
    deployment_status: str
    message: str
