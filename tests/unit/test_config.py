# Owner: Hiba
"""Tests for Vault-first configuration."""

from pathlib import Path
from typing import Any, ClassVar, cast

import pytest
from pydantic import ValidationError

from app import config
from app.config import Settings


class FakeVaultClient:
    """Fake Vault client for configuration tests."""

    calls: ClassVar[list[dict[str, Any]]] = []

    def __init__(self, addr: str, token: str, timeout_seconds: float = 5.0) -> None:
        self.calls.append(
            {
                "addr": addr,
                "token": token,
                "timeout_seconds": timeout_seconds,
            }
        )

    def read_secret(self, path: str) -> dict[str, Any]:
        """Return fake application settings."""
        self.calls[-1]["path"] = path
        return {
            "database_url": "postgresql+asyncpg://db.example/concierge",
            "sync_database_url": "postgresql://db.example/concierge",
            "redis_url": "redis://redis.example:6379",
            "minio_endpoint": "minio.example:9000",
            "model_server_url": "http://modelserver:8010",
            "guardrails_url": "http://guardrails:8020",
            "widget_token_signing_key": "vault-widget-key",
            "widget_token_ttl_seconds": 900,
            "session_memory_ttl_seconds": 1800,
        }


def test_settings_requires_vault_bootstrap_env(monkeypatch: pytest.MonkeyPatch) -> None:
    """Settings should fail without Vault bootstrap values."""
    monkeypatch.delenv("VAULT_ADDR", raising=False)
    monkeypatch.delenv("VAULT_TOKEN", raising=False)
    settings_cls = cast(Any, Settings)

    with pytest.raises(ValidationError):
        settings_cls(_env_file=None)


def test_app_secrets_are_loaded_from_vault(monkeypatch: pytest.MonkeyPatch) -> None:
    """Application secrets come from Vault, not direct environment settings."""
    config.get_settings.cache_clear()
    config.get_app_secrets.cache_clear()
    FakeVaultClient.calls.clear()
    monkeypatch.setenv("VAULT_ADDR", "http://vault:8200")
    monkeypatch.setenv("VAULT_TOKEN", "test-token")
    monkeypatch.setenv("VAULT_APP_SECRET_PATH", "secret/data/concierge/app")
    monkeypatch.setattr(config, "VaultClient", FakeVaultClient)

    secrets = config.get_app_secrets()

    assert secrets.database_url == "postgresql+asyncpg://db.example/concierge"
    assert secrets.widget_token_signing_key.get_secret_value() == "vault-widget-key"
    assert FakeVaultClient.calls == [
        {
            "addr": "http://vault:8200",
            "token": "test-token",
            "timeout_seconds": 5.0,
            "path": "secret/data/concierge/app",
        }
    ]

    config.get_settings.cache_clear()
    config.get_app_secrets.cache_clear()


def test_env_example_contains_only_vault_bootstrap_values() -> None:
    """The committed env example must not carry app secrets directly."""
    env_example = Path(".env.example").read_text()

    assert "VAULT_ADDR=" in env_example
    assert "VAULT_TOKEN=" in env_example
    assert "VAULT_APP_SECRET_PATH=" in env_example
    assert "DATABASE_URL=" not in env_example
    assert "REDIS_URL=" not in env_example
    assert "MINIO_ENDPOINT=" not in env_example
    assert "MODEL_SERVER_URL=" not in env_example
    assert "GUARDRAILS_URL=" not in env_example
