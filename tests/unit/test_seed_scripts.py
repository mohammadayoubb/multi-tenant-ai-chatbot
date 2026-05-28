# Owner: Hiba
"""Tests for local development seed scripts."""

from scripts.seed_tenants import DEFAULT_RATE_LIMITS, DEMO_TENANT_NAMES
from scripts.vault_seed import build_app_secret_payload


def test_demo_tenant_seed_targets_two_tenants() -> None:
    """The demo seed should create stable Tenant A and Tenant B records."""
    assert DEMO_TENANT_NAMES == ("Tenant A", "Tenant B")
    assert {rate_limit.action for rate_limit in DEFAULT_RATE_LIMITS} == {"chat", "rag", "agent"}


def test_vault_seed_payload_matches_app_secret_schema() -> None:
    """Vault seed payload should match app.config.AppSecrets without Vault bootstrap values."""
    payload = build_app_secret_payload(widget_token_signing_key="local-dev-key")

    assert set(payload) == {
        "database_url",
        "sync_database_url",
        "redis_url",
        "minio_endpoint",
        "model_server_url",
        "guardrails_url",
        "widget_token_signing_key",
        "widget_token_ttl_seconds",
        "session_memory_ttl_seconds",
    }
    assert payload["widget_token_signing_key"] == "local-dev-key"
    assert "vault_token" not in payload
