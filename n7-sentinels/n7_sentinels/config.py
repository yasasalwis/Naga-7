from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # NATS
    NATS_URL: str = "nats://localhost:4222"

    # Agent Identity
    AGENT_TYPE: str = "sentinel"
    AGENT_SUBTYPE: str = "endpoint"
    AGENT_ID: str = "sentinel-1"  # Should be dynamic/generated
    ZONE: str = "default"

    CORE_API_URL: str = "http://localhost:8000/api/v1"

    # Deception Engine
    DECEPTION_ENABLED: bool = True
    DECEPTION_DECOY_DIR: str = "/tmp/n7_decoys"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
