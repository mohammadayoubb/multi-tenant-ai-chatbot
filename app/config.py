# Owner: Hiba
"""Application configuration.

Only Vault bootstrap settings are read from the environment. Application
connection strings and service credentials must come from Vault.
"""

from functools import lru_cache
from typing import Any, cast

from pydantic import BaseModel, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

from app.infra.vault import VaultClient


class Settings(BaseSettings):
    """Typed Vault bootstrap settings for the Concierge platform."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    vault_addr: str
    vault_token: SecretStr
    vault_app_secret_path: str = "secret/data/concierge/app"
    vault_timeout_seconds: float = 5.0


class AppSecrets(BaseModel):
    """Application settings resolved from Vault."""

    database_url: str
    sync_database_url: str
    redis_url: str
    minio_endpoint: str
    model_server_url: str
    guardrails_url: str
    widget_token_signing_key: SecretStr
    widget_token_ttl_seconds: int = 900
    session_memory_ttl_seconds: int = 1800


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached Vault bootstrap settings."""
    settings_cls = cast(Any, Settings)
    return cast(Settings, settings_cls())


@lru_cache(maxsize=1)
def get_app_secrets() -> AppSecrets:
    """Load application settings from Vault."""
    settings = get_settings()
    vault = VaultClient(
        addr=settings.vault_addr,
        token=settings.vault_token.get_secret_value(),
        timeout_seconds=settings.vault_timeout_seconds,
    )
    return AppSecrets.model_validate(vault.read_secret(settings.vault_app_secret_path))
