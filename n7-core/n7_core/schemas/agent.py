
from typing import Dict, Any, List, Optional
from uuid import UUID
from datetime import datetime
from pydantic import BaseModel, Field

class AgentBase(BaseModel):
    agent_type: str
    agent_subtype: str
    zone: str = "default"
    capabilities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)

class AgentRegister(AgentBase):
    pass

class AgentHeartbeat(BaseModel):
    agent_id: UUID
    status: str
    resource_usage: Dict[str, Any] = Field(default_factory=dict)

class Agent(AgentBase):
    id: UUID
    status: str
    last_heartbeat: datetime
    config_version: int
    resource_usage: Dict[str, Any]

    class Config:
        from_attributes = True
