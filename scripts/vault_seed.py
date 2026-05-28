# Owner: Hiba
"""Seed local Vault dev secrets."""

from __future__ import annotations

import argparse
import logging
import os
import secrets
from typing import Mapping

import hvac  # type: ignore[import-untyped]

from app.config import get_settings

LOGGER = logging.getLogger(__name__)

AppSecretValue = str | int


def build_app_secret_payload(
    widget_token_signing_key: str | None = None,
) -> dict[str, AppSecretValue]:
    """Build local development app secrets for Vault."""
    return {
        "database_url": _env("APP_DATABASE_URL", "postgresql+asyncpg://postgres:postgres@db:5432/concierge"),
        "sync_database_url": _env("APP_SYNC_DATABASE_URL", "postgresql://postgres:postgres@db:5432/concierge"),
        "redis_url": _env("APP_REDIS_URL", "redis://redis:6379"),
        "minio_endpoint": _env("APP_MINIO_ENDPOINT", "minio:9000"),
        "model_server_url": _env("APP_MODEL_SERVER_URL", "http://modelserver:8010"),
        "guardrails_url": _env("APP_GUARDRAILS_URL", "http://guardrails:8020"),
        "modelserver_service_token": _env(
            "APP_MODELSERVER_SERVICE_TOKEN",
            _env("MODELSERVER_SERVICE_TOKEN", "local-modelserver-token"),
        ),
        "guardrails_service_token": _env(
            "APP_GUARDRAILS_SERVICE_TOKEN",
            _env("GUARDRAILS_SERVICE_TOKEN", "local-guardrails-token"),
        ),
        "widget_token_signing_key": (
            widget_token_signing_key
            or os.getenv("APP_WIDGET_TOKEN_SIGNING_KEY")
            or secrets.token_urlsafe(32)
        ),
        "widget_token_ttl_seconds": _env_int("APP_WIDGET_TOKEN_TTL_SECONDS", 900),
        "session_memory_ttl_seconds": _env_int("APP_SESSION_MEMORY_TTL_SECONDS", 1800),
    }


def seed_vault_app_secrets(
    payload: Mapping[str, AppSecretValue] | None = None,
    path: str | None = None,
) -> str:
    """Write local development app secrets into Vault."""
    settings = get_settings()
    secret_path = path or settings.vault_app_secret_path
    secret_payload = dict(payload or build_app_secret_payload())
    client = hvac.Client(
        url=settings.vault_addr,
        token=settings.vault_token.get_secret_value(),
        timeout=settings.vault_timeout_seconds,
    )
    client.write(secret_path, data=secret_payload)
    return secret_path


def main() -> None:
    """Seed local development secrets into Vault."""
    parser = argparse.ArgumentParser(description="Seed local app secrets into Vault.")
    parser.add_argument("--path", default=None, help="Override VAULT_APP_SECRET_PATH.")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    payload = build_app_secret_payload()
    secret_path = seed_vault_app_secrets(payload=payload, path=args.path)
    LOGGER.info("Seeded %s app secret keys into Vault at %s", len(payload), secret_path)


def _env(name: str, default: str) -> str:
    """Read one local development override."""
    return os.getenv(name, default)


def _env_int(name: str, default: int) -> int:
    """Read one positive integer local development override."""
    value = os.getenv(name)
    if value is None:
        return default
    parsed_value = int(value)
    if parsed_value <= 0:
        raise ValueError(f"{name} must be positive")
    return parsed_value


if __name__ == "__main__":
    main()
