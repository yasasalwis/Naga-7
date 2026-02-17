
from fastapi import APIRouter, Depends, HTTPException, status
from typing import List
from sqlalchemy import select
from datetime import datetime
from uuid import UUID

from ..auth import get_current_active_user
from ...database.session import async_session_maker
from ...models.agent import Agent as AgentModel
from ...schemas.agent import Agent, AgentRegister, AgentHeartbeat

router = APIRouter(prefix="/agents", tags=["Agents"])

@router.get("/", response_model=List[Agent])
async def list_agents(current_user = Depends(get_current_active_user)):
    async with async_session_maker() as session:
        result = await session.execute(select(AgentModel))
        return result.scalars().all()

@router.post("/register", response_model=Agent)
async def register_agent(agent_in: AgentRegister, current_user = Depends(get_current_active_user)):
    # Note: Authorization for agents might need a different dependency than user auth.
    # For now, reusing user auth or assuming header check if we change dependency.
    # In production, agents should use Mutual TLS or API Key.
    
    async with async_session_maker() as session:
        # Check if exists (optional logic, usually agents generate new ID or send existing)
        # Here we create new for simplicity or could look up by metadata if needed.
        
        db_agent = AgentModel(
            agent_type=agent_in.agent_type,
            agent_subtype=agent_in.agent_subtype,
            zone=agent_in.zone,
            capabilities=agent_in.capabilities,
            metadata_=agent_in.metadata, # Note: mapped to metadata_ in model
            status="active",
            last_heartbeat=datetime.utcnow()
        )
        session.add(db_agent)
        await session.commit()
        await session.refresh(db_agent)
        return db_agent

@router.post("/heartbeat")
async def heartbeat(heartbeat_in: AgentHeartbeat, current_user = Depends(get_current_active_user)):
    async with async_session_maker() as session:
        result = await session.execute(select(AgentModel).where(AgentModel.id == heartbeat_in.agent_id))
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        
        agent.last_heartbeat = datetime.utcnow()
        agent.status = heartbeat_in.status
        agent.resource_usage = heartbeat_in.resource_usage
        await session.commit()
        return {"status": "ok"}
