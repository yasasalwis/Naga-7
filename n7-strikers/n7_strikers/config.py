from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

# Resolve .env relative to the n7-strikers package root (two levels up from this file)
_ENV_FILE = Path(__file__).resolve().parent.parent / ".env"


class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"

    # NATS — populated from remote config on startup; empty until then
    NATS_URL: str = ""

    # Agent Identity — AGENT_ID is assigned by Core on registration (see agent_id.py)
    AGENT_TYPE: str = "striker"
    AGENT_SUBTYPE: str = "endpoint"
    ZONE: str = "default"

    CORE_API_URL: str  # Required

    # Authentication - Unique API key per agent instance
    API_KEY_FILE: str = ".agent_api_key"  # Local file to persist API key

    CAPABILITIES: list[str] = ["kill_process", "block_ip", "isolate_host", "unisolate_host"]

    model_config = SettingsConfigDict(env_file=str(_ENV_FILE), env_file_encoding="utf-8", extra="ignore")


settings = Settings()
