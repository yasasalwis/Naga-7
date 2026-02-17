
from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from ...schemas.event import Event
from ...models.event import Event as EventModel
from ...database.session import async_session_maker
from sqlalchemy import select
from ..auth import get_current_active_user

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
