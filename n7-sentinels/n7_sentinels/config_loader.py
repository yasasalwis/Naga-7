"""
Remote config loader for N7 agents.

On startup the agent calls GET {CORE_API_URL}/agent-config/{agent_id}/config with its API key.
CORE_API_URL already includes the versioned prefix (e.g. http://host:8000/api/v1).
Core responds with config values where the two sensitive fields (nats_url_enc,
core_api_url_enc) are Fernet-encrypted using a key derived from the agent's own
API key.  The agent decrypts them locally using the same derivation:
    key = base64url(sha256(api_key))

All other fields are returned as plaintext.
"""
import base64
import hashlib
import logging
from typing import Optional

import aiohttp
from cryptography.fernet import Fernet

logger = logging.getLogger("n7-sentinel.config-loader")


def _derive_fernet_key(secret: str) -> bytes:
    digest = hashlib.sha256(secret.encode()).digest()
    return base64.urlsafe_b64encode(digest)


async def fetch_remote_config(
    core_api_url: str,
    agent_id: str,
    api_key: str,
    session: Optional[aiohttp.ClientSession] = None,
) -> Optional[dict]:
    """
    Fetch and decrypt the centralized config for this agent from Core.

    Returns a dict with all config fields, sensitive ones already decrypted.
    Returns None on any failure (network error, 404, auth failure) — the caller
    should fall back to local .env values in that case.
    """
    url = f"{core_api_url}/agent-config/{agent_id}/config"
    headers = {"X-Agent-API-Key": api_key}

    own_session = session is None
    if own_session:
        session = aiohttp.ClientSession()

    try:
        async with session.get(url, headers=headers, timeout=aiohttp.ClientTimeout(total=10)) as resp:
            if resp.status == 404:
                logger.info("No remote config provisioned yet — using local .env values.")
                return None
            if resp.status != 200:
                logger.warning(f"Config fetch failed: HTTP {resp.status}")
                return None

            data = await resp.json()

        # Decrypt the two sensitive fields using the agent's own key
        fernet = Fernet(_derive_fernet_key(api_key))
        config = dict(data)

        if config.get("nats_url_enc"):
            try:
                config["nats_url"] = fernet.decrypt(config["nats_url_enc"].encode()).decode()
            except Exception as e:
                logger.error(f"Failed to decrypt nats_url: {e}")
                config["nats_url"] = None

        if config.get("core_api_url_enc"):
            try:
                config["core_api_url"] = fernet.decrypt(config["core_api_url_enc"].encode()).decode()
            except Exception as e:
                logger.error(f"Failed to decrypt core_api_url: {e}")
                config["core_api_url"] = None

        # Remove the encrypted blobs — callers only need the plaintext
        config.pop("nats_url_enc", None)
        config.pop("core_api_url_enc", None)

        logger.info(
            f"Remote config loaded (version {config.get('config_version', '?')}): "
            f"zone={config.get('zone')}, log_level={config.get('log_level')}, "
            f"probe_interval={config.get('probe_interval_seconds')}s"
        )
        return config

    except aiohttp.ClientError as e:
        logger.warning(f"Could not reach Core for config ({type(e).__name__}: {e}) — using local .env values.")
        return None
    except Exception as e:
        logger.error(f"Unexpected error fetching remote config: {e}", exc_info=True)
        return None
    finally:
        if own_session:
            await session.close()
