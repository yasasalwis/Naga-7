"""
Agent ID store for N7 Striker.

The agent's UUID is assigned by Core on first registration and persisted locally
so subsequent restarts reuse the same identity (Core recognises the API key and
returns the same DB record, but having the ID on disk avoids a round-trip before
other services need it).

Usage:
    from n7_strikers.agent_id import get_agent_id, set_agent_id
"""
import logging
import os
from pathlib import Path

_AGENT_ID_FILE = ".agent_id"
_agent_id: str | None = None

logger = logging.getLogger("n7-striker.agent-id")


def load_persisted_agent_id() -> str | None:
    """Read agent ID from disk if it exists. Called once at startup."""
    global _agent_id
    p = Path(_AGENT_ID_FILE)
    if p.exists():
        try:
            val = p.read_text().strip()
            if val:
                _agent_id = val
                logger.info(f"Loaded persisted agent ID: {_agent_id}")
                return _agent_id
        except Exception as e:
            logger.warning(f"Could not read agent ID file: {e}")
    return None


def set_agent_id(agent_id: str) -> None:
    """Set the agent ID (called after Core assigns it) and persist to disk."""
    global _agent_id
    _agent_id = agent_id
    try:
        p = Path(_AGENT_ID_FILE)
        p.write_text(agent_id)
        os.chmod(p, 0o600)
        logger.info(f"Agent ID set and persisted: {agent_id}")
    except Exception as e:
        logger.error(f"Failed to persist agent ID: {e}")


def get_agent_id() -> str | None:
    """Return the current agent ID, or None if not yet assigned."""
    return _agent_id
