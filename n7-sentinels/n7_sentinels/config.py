import uuid
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # NATS
    NATS_URL: str  # Required

    # Agent Identity
    AGENT_TYPE: str = "sentinel"
    AGENT_SUBTYPE: str = "endpoint"
    AGENT_ID: str = str(uuid.uuid4())  # Generated unique ID
    ZONE: str = "default"

    CORE_API_URL: str  # Required

    # Deception Engine
    DECEPTION_ENABLED: bool = True
    DECEPTION_DECOY_DIR: str = "/tmp/n7_decoys"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
