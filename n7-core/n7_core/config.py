
from typing import Literal, Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import PostgresDsn, RedisDsn

class Settings(BaseSettings):
    """
    Application Configuration.
    Reads from environment variables and .env file.
    """
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", case_sensitive=False)

    # Functionality
    ENVIRONMENT: Literal["development", "production", "testing"] = "development"
    DEBUG: bool = False
    LOG_LEVEL: str = "INFO"

    # API
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    SECRET_KEY: str = "changeme_in_production"

    # Database
    DATABASE_URL: PostgresDsn = "postgresql+asyncpg://n7:n7password@localhost:5432/n7_core"

    # Message Bus (NATS)
    NATS_URL: str = "nats://localhost:4222"
    NATS_CLUSTER_ID: str = "n7-cluster"
    NATS_CLIENT_ID: str = "n7-core-1"

    # Redis (Cache)
    REDIS_URL: RedisDsn = "redis://localhost:6379/0"

settings = Settings()
