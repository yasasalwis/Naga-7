from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration for Sentinel Agent Runtime.
    Reads from environment variables and .env file.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    # Agent Identity
    AGENT_TYPE: Literal["sentinel", "striker"] = "sentinel"
    AGENT_SUBTYPE: str = "system"  # Default subtype
    ZONE: str = "default"

    # Core API
    CORE_API_URL: str  # Required

    # NATS Configuration
    NATS_URL: str  # Required
    NATS_CLUSTER_ID: str = "n7-cluster"

    # Authentication - Unique API key per agent instance
    API_KEY_FILE: str = ".agent_api_key"  # Local file to persist API key

    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()
