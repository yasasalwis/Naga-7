from datetime import datetime
from typing import Dict, Any, List
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AgentBase(BaseModel):
    agent_type: str
    agent_subtype: str
    zone: str = "default"
    capabilities: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class AgentRegister(AgentBase):
    api_key: str  # Agent's self-generated unique API key


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

    @model_validator(mode='before')
    @classmethod
    def map_metadata_field(cls, data: Any):
        """Map metadata_ to metadata when loading from SQLAlchemy models."""
        if hasattr(data, 'metadata_'):
            # Convert SQLAlchemy model to dict with proper field mapping
            result = {
                "id": data.id,
                "agent_type": data.agent_type,
                "agent_subtype": data.agent_subtype,
                "zone": data.zone,
                "capabilities": data.capabilities,
                "metadata": data.metadata_,
                "status": data.status,
                "last_heartbeat": data.last_heartbeat,
                "config_version": data.config_version,
                "resource_usage": data.resource_usage,
            }
            return result
        return data
