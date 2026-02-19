from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration for Sentinel Event Emitter.
    Reads from environment variables and .env file.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    # Agent Identity
    AGENT_TYPE: Literal["sentinel", "striker"] = "sentinel"
    AGENT_SUBTYPE: str = "system"  # Default subtype

    # NATS Configuration
    NATS_URL: str  # Required
    NATS_CLUSTER_ID: str = "n7-cluster"

    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()
