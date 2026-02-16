
from fastapi import APIRouter, Depends, Query
from typing import List, Optional
from ...schemas.event import Event
from ..auth import get_current_active_user

router = APIRouter(prefix="/events", tags=["Events"])

@router.get("/", response_model=List[Event])
async def list_events(
    skip: int = 0, 
    limit: int = 100, 
    current_user = Depends(get_current_active_user)
):
    # TODO: Implement DB query
    return []
