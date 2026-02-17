from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # NATS
    NATS_URL: str = "nats://localhost:4222"

    # Agent Identity
    AGENT_TYPE: str = "striker"
    AGENT_SUBTYPE: str = "endpoint"
    AGENT_ID: str = "striker-1"  # Should be dynamic/generated
    ZONE: str = "default"

    CORE_API_URL: str = "http://localhost:8000/api"

    # Authentication - Unique API key per agent instance
    API_KEY_FILE: str = ".agent_api_key"  # Local file to persist API key

    CAPABILITIES: list[str] = ["kill_process", "block_ip"]

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")


settings = Settings()
