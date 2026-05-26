# Owner: Amer
"""Unit tests for the widget service helpers.

Covers FR-002 origin canonicalization (case-insensitive host, port exact,
scheme exact, path/query/fragment ignored, no subdomain rollup) and FR-009
TTL configurability.
"""

from __future__ import annotations

from uuid import uuid4

import jwt
import pytest

from app.services.widget_service import _canonicalize_origin
from app.services.widget_settings import widget_settings


# ---------------- Origin canonicalization ----------------


@pytest.mark.parametrize(
    "raw, expected",
    [
        ("https://customer-site.example", "https://customer-site.example"),
        ("https://Customer-Site.Example", "https://customer-site.example"),  # case
        ("https://customer-site.example/some/path", "https://customer-site.example"),
        ("https://customer-site.example?q=1", "https://customer-site.example"),
        ("https://customer-site.example#frag", "https://customer-site.example"),
        ("https://customer-site.example:443", "https://customer-site.example"),  # default port stripped
        ("http://customer-site.example:80", "http://customer-site.example"),
        ("http://customer-site.example:8080", "http://customer-site.example:8080"),
        ("https://customer-site.example:8443", "https://customer-site.example:8443"),
    ],
)
def test_canonicalize_accepts(raw: str, expected: str) -> None:
    assert _canonicalize_origin(raw) == expected


@pytest.mark.parametrize(
    "raw",
    [
        "",
        "not-a-url",
        "ftp://customer-site.example",
        "file:///etc/passwd",
        "https://",
        "javascript:alert(1)",
    ],
)
def test_canonicalize_rejects(raw: str) -> None:
    assert _canonicalize_origin(raw) is None


def test_subdomain_does_not_match_parent() -> None:
    """FR-002 strict-host: subdomain canonicalization differs from parent."""
    assert (
        _canonicalize_origin("https://customer-site.example")
        != _canonicalize_origin("https://www.customer-site.example")
    )


def test_different_scheme_does_not_match() -> None:
    assert (
        _canonicalize_origin("http://customer-site.example")
        != _canonicalize_origin("https://customer-site.example")
    )


def test_different_port_does_not_match() -> None:
    assert (
        _canonicalize_origin("https://customer-site.example:443")
        != _canonicalize_origin("https://customer-site.example:8443")
    )


# ---------------- TTL configurability (FR-009, FR-018) ----------------


def test_token_ttl_reads_from_settings(monkeypatch) -> None:
    """Setting WIDGET_TOKEN_TTL_SECONDS at construction time changes the exp claim."""
    from app.services import widget_settings as ws_module

    # Reset the lru_cache so a fresh settings object is constructed.
    ws_module.widget_settings.cache_clear()
    monkeypatch.setenv("WIDGET_TOKEN_TTL_SECONDS", "120")
    try:
        from app.repositories.widget_repo import InMemoryWidgetRepository
        from app.services.rate_limiter import InMemoryTokenBucketRateLimiter
        from app.services.widget_service import WidgetTokenService

        service = WidgetTokenService(
            repo=InMemoryWidgetRepository(),
            per_ip_limiter=InMemoryTokenBucketRateLimiter(
                capacity=10000, refill_per_second=10000.0
            ),
            per_widget_limiter=InMemoryTokenBucketRateLimiter(
                capacity=10000, refill_per_second=10000.0
            ),
        )

        token = service._mint_jwt(
            tenant_id=uuid4(),
            widget_id=uuid4(),
            origin="http://localhost:5500",
            session_id=uuid4(),
        )
        claims = jwt.decode(
            token, widget_settings().widget_jwt_secret, algorithms=["HS256"]
        )
        assert claims["exp"] - claims["iat"] == 120
    finally:
        # Restore default for subsequent tests.
        ws_module.widget_settings.cache_clear()
