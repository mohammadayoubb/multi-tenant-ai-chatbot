# Owner: Hiba
"""Application configuration.

This is the only allowed place for environment settings.
"""

from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Typed settings for the Concierge platform."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = Field(default="postgresql+asyncpg://postgres:postgres@localhost:5432/concierge")
    sync_database_url: str = Field(default="postgresql://postgres:postgres@localhost:5432/concierge")
    redis_url: str = Field(default="redis://localhost:6379")
    minio_endpoint: str = Field(default="localhost:9000")
    vault_addr: str = Field(default="http://localhost:8200")
    vault_root_token: str = Field(default="root")
    model_server_url: str = Field(default="http://localhost:8010")
    guardrails_url: str = Field(default="http://localhost:8020")
    modelserver_service_token: str = Field(default="")
    guardrails_service_token: str = Field(default="")
    widget_token_ttl_seconds: int = 900
    session_memory_ttl_seconds: int = 1800


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings."""
    return Settings()
