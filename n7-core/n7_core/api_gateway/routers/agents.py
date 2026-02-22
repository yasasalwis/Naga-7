import json
import logging
import uuid as _uuid
from datetime import datetime, timedelta, UTC
from typing import List

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select

from ..auth import get_agent_from_api_key, get_current_active_user, pwd_context
from ...config_sync.service import ConfigSyncService
from ...database.session import async_session_maker
from ...messaging.nats_client import nats_client
from ...models.agent import Agent as AgentModel
from ...models.agent_config import AgentConfig
from ...schemas.agent import Agent, AgentRegister, AgentRegisterResponse, AgentHeartbeat, AgentConfigUpdate, AgentUpdate

router = APIRouter(tags=["Agents"])

AGENT_STALE_THRESHOLD_SECONDS = 90

logger = logging.getLogger("n7-core.agents-router")

_config_sync = ConfigSyncService()


async def _push_config_to_agent(agent_id: str, cfg) -> None:
    """
    Publish the updated config snapshot to the agent via NATS so it applies
    immediately instead of waiting for the 60-second poll cycle.
    Subject: n7.config.<agent_id>
    Fails silently — agents fall back to their poll loop if NATS is unavailable.
    """
    if not nats_client.nc.is_connected:
        return
    try:
        payload = {
            "config_version":        cfg.config_version,
            "zone":                  cfg.zone,
            "log_level":             cfg.log_level,
            "probe_interval_seconds": cfg.probe_interval_seconds,
            "detection_thresholds":  cfg.detection_thresholds or {},
            "enabled_probes":        cfg.enabled_probes or [],
            "capabilities":          cfg.capabilities or [],
            "allowed_actions":       cfg.allowed_actions,
            "action_defaults":       cfg.action_defaults or {},
            "max_concurrent_actions": cfg.max_concurrent_actions,
        }
        subject = f"n7.config.{agent_id}"
        await nats_client.nc.publish(subject, json.dumps(payload).encode())
        logger.info(f"Pushed config version {cfg.config_version} to {subject}")
    except Exception as e:
        logger.warning(f"Failed to push config to agent {agent_id} via NATS: {e}")


@router.get("/", response_model=List[Agent])
async def list_agents():
    async with async_session_maker() as session:
        result = await session.execute(select(AgentModel))
        agents = result.scalars().all()

    # Mark agents whose last heartbeat exceeds the stale threshold as inactive
    stale_cutoff = datetime.now(UTC) - timedelta(seconds=AGENT_STALE_THRESHOLD_SECONDS)
    for agent in agents:
        if agent.last_heartbeat:
            hb = agent.last_heartbeat
            if hb.tzinfo is None:
                hb = hb.replace(tzinfo=UTC)
            if hb < stale_cutoff:
                agent.status = "inactive"

    return agents


@router.get("/strikers")
async def list_strikers():
    """
    Return all striker agents with their current status and capabilities.
    Used by the dashboard to show which strikers are available for operator dispatch.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(AgentModel).where(AgentModel.agent_type == "striker")
        )
        strikers = result.scalars().all()

    stale_cutoff = datetime.now(UTC) - timedelta(seconds=AGENT_STALE_THRESHOLD_SECONDS)
    out = []
    for s in strikers:
        status = s.status
        if s.last_heartbeat:
            hb = s.last_heartbeat
            if hb.tzinfo is None:
                hb = hb.replace(tzinfo=UTC)
            if hb < stale_cutoff:
                status = "inactive"
        out.append({
            "id": str(s.id),
            "agent_subtype": s.agent_subtype,
            "zone": s.zone,
            "status": status,
            "capabilities": s.capabilities or [],
            "last_heartbeat": s.last_heartbeat.isoformat() if s.last_heartbeat else None,
        })
    return out


_MTLS_PORT = 8443


@router.post("/register", response_model=AgentRegisterResponse)
async def register_agent(request: Request, agent_in: AgentRegister):
    """
    Register a new agent. No authentication required for initial registration.
    Agent sends its self-generated API key which is hashed and stored.
    Registration is available on the plain HTTP port (8000) because agents have
    no cert yet — this endpoint is the cert issuance point. After registration
    agents switch to the mTLS port (8443) for all subsequent communication.
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
                # Valid re-registration, update status and return fresh cert
                existing_agent.last_heartbeat = datetime.now(UTC)
                existing_agent.status = "active"
                existing_agent.capabilities = agent_in.capabilities
                existing_agent.metadata_ = agent_in.metadata

                await session.commit()
                await session.refresh(existing_agent)

                from ..ca import generate_agent_cert, get_ca_cert_pem
                try:
                    cert, key = generate_agent_cert(str(existing_agent.id))
                    response_data = AgentRegisterResponse.model_validate(existing_agent)
                    response_data.client_cert = cert
                    response_data.client_key = key
                    response_data.ca_cert = get_ca_cert_pem()
                    return response_data
                except Exception as e:
                    logger.error(f"Failed to generate mTLS certificates for agent {existing_agent.id}: {e}")
                    return AgentRegisterResponse.model_validate(existing_agent)
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
            last_heartbeat=datetime.now(UTC)
        )
        session.add(db_agent)
        await session.commit()
        await session.refresh(db_agent)
        
        # Generate mTLS certificates for the agent
        from ..ca import generate_agent_cert, get_ca_cert_pem
        try:
            cert, key = generate_agent_cert(str(db_agent.id))
            response_data = AgentRegisterResponse.model_validate(db_agent)
            response_data.client_cert = cert
            response_data.client_key = key
            response_data.ca_cert = get_ca_cert_pem()
            return response_data
        except Exception as e:
            logger.error(f"Failed to generate mTLS certificates for agent {db_agent.id}: {e}")
            return AgentRegisterResponse.model_validate(db_agent)


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
        agent.last_heartbeat = datetime.now(UTC)
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
    Returns type-specific fields based on the agent's registered agent_type.
    """
    async with async_session_maker() as session:
        result = await session.execute(
            select(AgentConfig).where(AgentConfig.agent_id == _uuid.UUID(agent_id))
        )
        cfg = result.scalar_one_or_none()

        # Also fetch the agent record to know the type
        agent_result = await session.execute(
            select(AgentModel).where(AgentModel.id == _uuid.UUID(agent_id))
        )
        agent = agent_result.scalar_one_or_none()

    agent_type = agent.agent_type if agent else ""

    if not cfg:
        # Return a type-appropriate default config shell so the dashboard can
        # render the correct form and the operator can save an initial configuration.
        base = {
            "agent_id": agent_id,
            "agent_type": agent_type,
            "config_version": 0,
            "zone": "default",
            "log_level": "INFO",
            "environment": "production",
        }
        if agent_type == "sentinel":
            base.update({
                "probe_interval_seconds": 10,
                "detection_thresholds": {
                    "cpu_threshold": 80,
                    "mem_threshold": 85,
                    "disk_threshold": 90,
                    "load_multiplier": 2.0,
                },
                "enabled_probes": ["system", "network", "process", "file"],
            })
        elif agent_type == "striker":
            base.update({
                "capabilities": ["network_block", "process_kill", "file_quarantine"],
                "allowed_actions": None,
                "action_defaults": {"network_block": {"duration": 3600}},
                "max_concurrent_actions": None,
            })
        return base

    response = {
        "agent_id": agent_id,
        "agent_type": agent_type,
        "config_version": cfg.config_version,
        "zone": cfg.zone,
        "log_level": cfg.log_level,
        "environment": cfg.environment,
    }
    if agent_type == "sentinel":
        response.update({
            "probe_interval_seconds": cfg.probe_interval_seconds,
            "detection_thresholds": cfg.detection_thresholds or {},
            "enabled_probes": cfg.enabled_probes or [],
        })
    elif agent_type == "striker":
        response.update({
            "capabilities": cfg.capabilities or [],
            "allowed_actions": cfg.allowed_actions,
            "action_defaults": cfg.action_defaults or {},
            "max_concurrent_actions": cfg.max_concurrent_actions,
        })
    return response


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
            agent_type=agent.agent_type,
        )
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    await _push_config_to_agent(agent_id, updated_cfg)

    return {
        "agent_id": agent_id,
        "config_version": updated_cfg.config_version,
        "updated_fields": list(update_dict.keys()),
        "message": "Config updated and pushed to agent via NATS.",
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
            updated_cfg = await _config_sync.upsert_config(
                agent_id=_uuid.UUID(agent_id),
                config_dict=config_fields,
                agent_type=agent.agent_type,
            )
            await _push_config_to_agent(agent_id, updated_cfg)
        except ValueError:
            logger.warning(
                f"No AgentConfig provisioned for agent {agent_id}; "
                "agent table updated only. Config changes will apply after deployment."
            )

    return agent
