
from typing import Literal
from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    """
    Sentinel Configuration.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    # Functionality
    ENVIRONMENT: Literal["development", "production", "testing"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"
    
    # Identity
    AGENT_TYPE: str = "sentinel"
    AGENT_SUBTYPE: str = "network"
    AGENT_ZONE: str = "default"

    # Core Connection
    CORE_API_URL: str = "http://localhost:8000"
    CORE_API_KEY: str = "secret-api-key" # For initial auth or mTLS

    # Message Bus
    NATS_URL: str = "nats://localhost:4222"

settings = Settings()
