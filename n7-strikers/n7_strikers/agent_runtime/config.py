from pathlib import Path
from typing import Literal, List

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to the n7-strikers package root (three levels up from this file)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    """
    Configuration for Striker Agent Runtime.
    Reads from environment variables and .env file.
    """
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    # Agent Identity — AGENT_ID is assigned by Core on registration (see agent_id.py)
    AGENT_TYPE: Literal["sentinel", "striker"] = "striker"
    AGENT_SUBTYPE: str = "network"  # Default subtype
    ZONE: str = "default"

    # Capabilities
    CAPABILITIES: List[str] = ["network_block", "process_kill", "file_quarantine"]

    # Core API
    CORE_API_URL: str  # Required

    # NATS Configuration — populated from remote config on startup; empty until then
    NATS_URL: str = ""
    NATS_CLUSTER_ID: str = "n7-cluster"
    
    # Authentication - Unique API key per agent instance
    API_KEY_FILE: str = ".agent_api_key"  # Local file to persist API key

    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()
