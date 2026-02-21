import logging
import uuid as _uuid
from datetime import datetime, timedelta
from typing import List

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select

from ..auth import get_agent_from_api_key, get_current_active_user, pwd_context
from ...config_sync.service import ConfigSyncService
from ...database.session import async_session_maker
from ...models.agent import Agent as AgentModel
from ...models.agent_config import AgentConfig
from ...schemas.agent import Agent, AgentRegister, AgentHeartbeat, AgentConfigUpdate, AgentUpdate

router = APIRouter(tags=["Agents"])

AGENT_STALE_THRESHOLD_SECONDS = 90

logger = logging.getLogger("n7-core.agents-router")

_config_sync = ConfigSyncService()


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

    NOTE: This is the HTTP fallback path. Agents prefer NATS heartbeats
    (n7.heartbeat.sentinel.{id} / n7.heartbeat.striker.{id}) when NATS is available.
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


@router.get("/{agent_id}/config")
async def get_agent_config_meta(
    agent_id: str,
    current_user=Depends(get_current_active_user),
):
    """
    Return non-sensitive config fields for dashboard display.
    User-authenticated (JWT Bearer). Does NOT return encrypted NATS/API URLs.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(AgentConfig).where(AgentConfig.agent_id == _uuid.UUID(agent_id))
        )
        cfg = result.scalar_one_or_none()

    if not cfg:
        raise HTTPException(status_code=404, detail="No config found for this agent.")

    return {
        "agent_id": agent_id,
        "config_version": cfg.config_version,
        "zone": cfg.zone,
        "log_level": cfg.log_level,
        "probe_interval_seconds": cfg.probe_interval_seconds,
        "detection_thresholds": cfg.detection_thresholds or {},
        "capabilities": cfg.capabilities or [],
        "environment": cfg.environment,
    }


@router.put("/{agent_id}/config")
async def update_agent_config(
    agent_id: str,
    config_update: AgentConfigUpdate,
    current_user=Depends(get_current_active_user),
):
    """
    Update agent configuration fields. User-authenticated (JWT Bearer).
    Increments config_version automatically so the agent detects the change
    on its next config poll cycle (every 60s).
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(AgentModel).where(AgentModel.id == _uuid.UUID(agent_id))
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

    update_dict = config_update.model_dump(exclude_none=True)
    if not update_dict:
        raise HTTPException(status_code=422, detail="No fields to update.")

    try:
        updated_cfg = await _config_sync.upsert_config(
            agent_id=_uuid.UUID(agent_id),
            config_dict=update_dict,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    return {
        "agent_id": agent_id,
        "config_version": updated_cfg.config_version,
        "updated_fields": list(update_dict.keys()),
        "message": "Config updated. Agent will reload on next config poll cycle (~60s).",
    }


@router.put("/{agent_id}", response_model=Agent)
async def update_agent(
    agent_id: str,
    agent_update: AgentUpdate,
    current_user=Depends(get_current_active_user),
):
    """
    Update agent record (subtype, zone, capabilities) and propagate behavioural config
    changes to AgentConfig so the agent reloads on its next poll cycle.
    User-authenticated (JWT Bearer).
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(AgentModel).where(AgentModel.id == _uuid.UUID(agent_id))
        )
        agent = result.scalar_one_or_none()
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")

        if agent_update.agent_subtype is not None:
            agent.agent_subtype = agent_update.agent_subtype
        if agent_update.zone is not None:
            agent.zone = agent_update.zone
        if agent_update.capabilities is not None:
            agent.capabilities = agent_update.capabilities

        await session.commit()
        await session.refresh(agent)

    # Propagate config-level changes to AgentConfig (triggers agent reload)
    config_fields: dict = {}
    if agent_update.zone is not None:
        config_fields["zone"] = agent_update.zone
    if agent_update.capabilities is not None:
        config_fields["capabilities"] = agent_update.capabilities
    if agent_update.detection_thresholds is not None:
        config_fields["detection_thresholds"] = agent_update.detection_thresholds
    if agent_update.probe_interval_seconds is not None:
        config_fields["probe_interval_seconds"] = agent_update.probe_interval_seconds

    if config_fields:
        try:
            await _config_sync.upsert_config(
                agent_id=_uuid.UUID(agent_id),
                config_dict=config_fields,
            )
        except ValueError:
            logger.warning(
                f"No AgentConfig provisioned for agent {agent_id}; "
                "agent table updated only. Config changes will apply after deployment."
            )

    return agent
