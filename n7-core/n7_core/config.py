from typing import Literal

from pydantic import PostgresDsn, RedisDsn
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Application Configuration.
    Reads from environment variables and .env file.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False, extra="ignore")

    # Functionality
    ENVIRONMENT: Literal["development", "production", "testing"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    SECRET_KEY: str  # Required

    # Database
    DATABASE_URL: PostgresDsn  # Required

    # Message Bus (NATS)
    NATS_URL: str  # Required
    NATS_CLUSTER_ID: str = "n7-cluster"
    NATS_CLIENT_ID: str = "n7-core-1"

    # Redis (Cache)
    REDIS_URL: RedisDsn  # Required

    # LLM Analyzer (Ollama — runs locally for on-premise data security)
    OLLAMA_URL: str  # Required
    OLLAMA_MODEL: str = "llama3"

    # Threat Intelligence Feed Ingestion
    OTX_API_KEY: str = ""          # Set via environment variable OTX_API_KEY
    TI_FETCH_INTERVAL: int = 3600  # Seconds between TI feed refresh cycles (1 hour)
    TI_IOC_TTL: int = 86400        # Redis TTL for feed-sourced IOCs (24 hours)


settings = Settings()
