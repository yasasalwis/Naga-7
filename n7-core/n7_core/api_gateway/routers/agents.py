from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ..auth import get_agent_from_api_key, pwd_context
from ...database.session import async_session_maker
from ...models.agent import Agent as AgentModel
from ...schemas.agent import Agent, AgentRegister, AgentHeartbeat

router = APIRouter(tags=["Agents"])

AGENT_STALE_THRESHOLD_SECONDS = 90


@router.get("/", response_model=List[Agent])
async def list_agents():
    async with async_session_maker() as session:
        result = await session.execute(select(AgentModel))
        agents = result.scalars().all()

    # Mark agents whose last heartbeat exceeds the stale threshold as inactive
    stale_cutoff = datetime.utcnow() - timedelta(seconds=AGENT_STALE_THRESHOLD_SECONDS)
    for agent in agents:
        if agent.last_heartbeat and agent.last_heartbeat < stale_cutoff:
            agent.status = "inactive"

    return agents


@router.post("/register", response_model=Agent)
async def register_agent(agent_in: AgentRegister):
    """
    Register a new agent. No authentication required for initial registration.
    Agent sends its self-generated API key which is hashed and stored.
    """
    async with async_session_maker() as session:
        # Extract prefix (first 16 chars) for O(1) indexed lookup
        api_key_prefix = agent_in.api_key[:16] if len(agent_in.api_key) >= 16 else agent_in.api_key

        # Check for existing agent with this prefix
        result = await session.execute(
            select(AgentModel).where(AgentModel.api_key_prefix == api_key_prefix)
        )
        existing_agent = result.scalar_one_or_none()

        if existing_agent:
            # Verify if it's the same key
            if pwd_context.verify(agent_in.api_key, existing_agent.api_key_hash):
                # Valid re-registration, update status and return
                existing_agent.last_heartbeat = datetime.utcnow()
                existing_agent.status = "active"
                # Update other fields if needed
                existing_agent.capabilities = agent_in.capabilities
                existing_agent.metadata_ = agent_in.metadata
                
                await session.commit()
                await session.refresh(existing_agent)
                return existing_agent
            else:
                # Key collision or invalid key for existing prefix
                # Since prefix is 16 chars, collision is unlikely. Assume invalid key.
                raise HTTPException(status_code=400, detail="API Key collision or invalid key for existing agent.")

        # Hash the API key before storing (never store plain-text)
        api_key_hash = pwd_context.hash(agent_in.api_key)

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
    The authenticated agent (resolved from API key) is the authoritative identity;
    the agent_id in the payload is verified to match but the DB lookup uses the
    authenticated agent's id to avoid 404s when the payload carries a stale id.
    """
    # Verify the payload agent_id matches the authenticated agent (security check)
    if str(heartbeat_in.agent_id) != str(authenticated_agent.id):
        raise HTTPException(
            status_code=403,
            detail="Agent ID mismatch - cannot update another agent's heartbeat"
        )

    async with async_session_maker() as session:
        result = await session.execute(
            select(AgentModel).where(AgentModel.id == authenticated_agent.id)
        )
        agent = result.scalar_one_or_none()

        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        # Update heartbeat
        agent.last_heartbeat = datetime.utcnow()
        agent.status = heartbeat_in.status
        agent.resource_usage = heartbeat_in.resource_usage
        await session.commit()
        return {"status": "ok"}
