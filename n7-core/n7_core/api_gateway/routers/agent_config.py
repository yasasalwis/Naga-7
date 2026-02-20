from fastapi import APIRouter, Depends, HTTPException, Security, status
from fastapi.security import APIKeyHeader

from ..auth import get_agent_from_api_key
from ...config_sync.service import ConfigSyncService
from ...models.agent import Agent as AgentModel

router = APIRouter(tags=["Agent Config"])

_config_sync = ConfigSyncService()

# Re-declare the header extractor so we can get the raw key alongside the authenticated agent
_agent_api_key_header = APIKeyHeader(name="X-Agent-API-Key", auto_error=True)


@router.get("/{agent_id}/config")
async def get_agent_config(
    agent_id: str,
    raw_api_key: str = Security(_agent_api_key_header),
    authenticated_agent: AgentModel = Depends(get_agent_from_api_key),
):
    """
    Fetch the centralized config for a deployed agent.

    Authentication: X-Agent-API-Key header (same key used for heartbeats).
    Authorization: agents can only fetch their own config.

    Returns config values where sensitive fields (nats_url_enc, core_api_url_enc)
    are Fernet-encrypted with a key derived from THIS agent's API key.
    The agent decrypts them locally using the same derivation: sha256(api_key).

    Also returns config_version so the agent can cache and only re-apply on change.
    """
    # Agents may only retrieve their own config
    if str(authenticated_agent.id) != agent_id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Agents may only retrieve their own configuration.",
        )

    config = await _config_sync.get_config_for_agent(
        agent_id=authenticated_agent.id,
        api_key=raw_api_key,
    )
    if config is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No configuration found for this agent. It may not have been provisioned yet.",
        )

    return config
