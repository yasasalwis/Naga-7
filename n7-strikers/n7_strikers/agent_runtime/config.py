from typing import Literal, List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Configuration for Striker Agent Runtime.
    Reads from environment variables and .env file.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    # Agent Identity
    AGENT_TYPE: Literal["sentinel", "striker"] = "striker"
    AGENT_SUBTYPE: str = "network"  # Default subtype
    AGENT_ID: str = "striker-001"  # Default ID, will be replaced after registration
    ZONE: str = "default"

    # Capabilities
    CAPABILITIES: List[str] = ["network_block", "process_kill", "file_quarantine"]

    # Core API
    CORE_API_URL: str = "http://localhost:8000/api"

    # NATS Configuration
    NATS_URL: str = "nats://localhost:4222"
    NATS_CLUSTER_ID: str = "n7-cluster"
    
    # Authentication - Unique API key per agent instance
    API_KEY_FILE: str = ".agent_api_key"  # Local file to persist API key

    # Logging
    LOG_LEVEL: str = "INFO"


settings = Settings()
