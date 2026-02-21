from typing import List
import json
import logging
from datetime import datetime
import uuid

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from sqlalchemy import select

from ...database.session import async_session_maker
from ...models.event import Event as EventModel
from ...schemas.event import Event
from ...messaging.nats_client import nats_client

logger = logging.getLogger("n7-core.events-router")

class StrikeRequest(BaseModel):
    action_type: str
    target: str

router = APIRouter(tags=["Events"])


@router.get("/", response_model=List[Event])
async def list_events(
        skip: int = 0,
        limit: int = 100
):
    async with async_session_maker() as session:
        result = await session.execute(
            select(EventModel)
            .offset(skip)
            .limit(limit)
            .order_by(EventModel.timestamp.desc())
        )
        events = result.scalars().all()
        return events


@router.post("/{event_id}/strike")
async def strike_event(event_id: str, req: StrikeRequest):
    """
    Dispatch an action via NATS to strikers based on an LLM recommendation.
    """
    action_id = str(uuid.uuid4())
    action_payload = {
        "action_id": action_id,
        "event_id": event_id,
        "type": req.action_type,
        "params": {
            "action_type": req.action_type,
            "target": req.target,
            "duration": 3600  # Default duration for network blocks
        },
        "timestamp": datetime.utcnow().isoformat()
    }
    
    if nats_client.nc and nats_client.nc.is_connected:
        await nats_client.nc.publish(
            "n7.actions.broadcast",
            json.dumps(action_payload).encode()
        )
        logger.info(f"Dispatched strike action {action_id} for event {event_id}: {req.action_type}")
        return {"status": "dispatched", "action_id": action_id}
    else:
        logger.error("Failed to dispatch strike: NATS not connected")
        raise HTTPException(status_code=503, detail="Messaging core (NATS) unavailable")
