
from fastapi import APIRouter, Depends
from typing import List
from ..auth import get_current_active_user

router = APIRouter(prefix="/agents", tags=["Agents"])

@router.get("/")
async def list_agents(current_user = Depends(get_current_active_user)):
    # TODO: Implement DB query for agents
    return []
