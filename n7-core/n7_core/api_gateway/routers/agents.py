from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ..auth import get_agent_from_api_key, pwd_context
from ...database.session import async_session_maker
from ...models.agent import Agent as AgentModel
from ...schemas.agent import Agent, AgentRegister, AgentHeartbeat

router = APIRouter(tags=["Agents"])


@router.get("/", response_model=List[Agent])
async def list_agents():
    async with async_session_maker() as session:
        result = await session.execute(select(AgentModel))
        return result.scalars().all()


@router.post("/register", response_model=Agent)
async def register_agent(agent_in: AgentRegister):
    """
    Register a new agent. No authentication required for initial registration.
    Agent sends its self-generated API key which is hashed and stored.
    """
    async with async_session_maker() as session:
        # Hash the API key before storing (never store plain-text)
        api_key_hash = pwd_context.hash(agent_in.api_key)

        # Extract prefix (first 16 chars) for O(1) indexed lookup
        api_key_prefix = agent_in.api_key[:16] if len(agent_in.api_key) >= 16 else agent_in.api_key

        db_agent = AgentModel(
            agent_type=agent_in.agent_type,
            agent_subtype=agent_in.agent_subtype,
            zone=agent_in.zone,
            capabilities=agent_in.capabilities,
            metadata_=agent_in.metadata,
            api_key_prefix=api_key_prefix,
            api_key_hash=api_key_hash,
            status="active",
            last_heartbeat=datetime.utcnow()
        )
        session.add(db_agent)
        await session.commit()
        await session.refresh(db_agent)
        return db_agent


@router.post("/heartbeat")
async def heartbeat(
        heartbeat_in: AgentHeartbeat,
        authenticated_agent: AgentModel = Depends(get_agent_from_api_key)
):
    """
    Heartbeat endpoint. Requires valid API key authentication.
    Verifies the authenticated agent matches the heartbeat agent_id.
    """
    async with async_session_maker() as session:
        # Fetch the agent from heartbeat payload
        result = await session.execute(
            select(AgentModel).where(AgentModel.id == heartbeat_in.agent_id)
        )
        agent = result.scalar_one_or_none()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Verify the authenticated agent matches the heartbeat agent_id (security check)
        if agent.id != authenticated_agent.id:
            raise HTTPException(
                status_code=403,
                detail="Agent ID mismatch - cannot update another agent's heartbeat"
            )

        # Update heartbeat
        agent.last_heartbeat = datetime.utcnow()
        agent.status = heartbeat_in.status
        agent.resource_usage = heartbeat_in.resource_usage
        await session.commit()
        return {"status": "ok"}
