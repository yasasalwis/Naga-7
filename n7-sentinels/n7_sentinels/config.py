from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    ENVIRONMENT: str = "development"
    LOG_LEVEL: str = "INFO"
    
    # NATS
    NATS_URL: str = "nats://localhost:4222"
    
    # Agent Identity
    AGENT_TYPE: str = "sentinel"
    AGENT_SUBTYPE: str = "endpoint"
    AGENT_ID: str = "sentinel-1" # Should be dynamic/generated
    ZONE: str = "default"

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

settings = Settings()
