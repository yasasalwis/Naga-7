from datetime import datetime
from typing import Dict, Any, List
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field


class Event(BaseModel):
    """
    Standardized Event Model.
    Ref: TDD Section 9.1.1 Event Data Model
    """
    model_config = ConfigDict(from_attributes=True)

    event_id: UUID = Field(default_factory=uuid4)
    timestamp: datetime = Field(default_factory=datetime.utcnow)
    sentinel_id: UUID
    event_class: str  # network, endpoint, cloud, application
    severity: str  # informational, low, medium, high, critical
    raw_data: Dict[str, Any]
    enrichments: Dict[str, Any] = Field(default_factory=dict)
    mitre_techniques: List[str] = Field(default_factory=list)


class Alert(BaseModel):
    """
    Alert Model.
    Ref: TDD Section 9.1.2 Alert Data Model
    """
    alert_id: UUID = Field(default_factory=uuid4)
    created_at: datetime = Field(default_factory=datetime.utcnow)
    event_ids: List[UUID]
    threat_score: int = Field(ge=0, le=100)
    severity: str
    status: str = "new"
    verdict: str = "pending"
    affected_assets: List[Dict[str, Any]] = Field(default_factory=list)
