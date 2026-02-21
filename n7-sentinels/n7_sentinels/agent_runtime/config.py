from pathlib import Path
from typing import Dict, List, Literal

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to the n7-sentinels package root (three levels up from this file)
_ENV_FILE = Path(__file__).resolve().parent.parent.parent / ".env"


class Settings(BaseSettings):
    """
    Configuration for Sentinel Agent Runtime.
    Reads from environment variables and .env file.
    """
    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    # Agent Identity
    AGENT_TYPE: Literal["sentinel", "striker"] = "sentinel"
    AGENT_SUBTYPE: str = "system"  # Default subtype
    ZONE: str = "default"

    # Core API
    CORE_API_URL: str  # Required

    # NATS Configuration — populated from remote config on startup; empty until then
    NATS_URL: str = ""
    NATS_CLUSTER_ID: str = "n7-cluster"

    # Authentication - Unique API key per agent instance
    API_KEY_FILE: str = ".agent_api_key"  # Local file to persist API key

    # Logging
    LOG_LEVEL: str = "INFO"

    # Sentinel-specific — populated from remote config; defaults used until first sync
    PROBE_INTERVAL_SECONDS: int = 10
    DETECTION_THRESHOLDS: Dict[str, float] = {
        "cpu_threshold": 80.0,
        "mem_threshold": 85.0,
        "disk_threshold": 90.0,
        "load_multiplier": 2.0,
    }
    ENABLED_PROBES: List[str] = ["system", "network", "process", "file"]


settings = Settings()
