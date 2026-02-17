from typing import List

from fastapi import APIRouter
from sqlalchemy import select

from ...database.session import async_session_maker
from ...models.event import Event as EventModel
from ...schemas.event import Event

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
