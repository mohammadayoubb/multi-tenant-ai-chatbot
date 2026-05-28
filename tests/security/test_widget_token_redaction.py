# Owner: Amer
"""Redaction tests for the widget token endpoint (SC-009, Constitution Principle V).

Captures the structured-log output across 100 refusal/success runs and asserts
NO raw widget_id, NO raw IP, NO JWT signing secret, NO raw token appears in
any emitted log record.
"""

from __future__ import annotations

import io
import json
import re
from uuid import UUID, uuid4

import pytest
import structlog
from fastapi.testclient import TestClient

import app.api.routes.widgets as widgets_route
from app.main import app
from app.repositories.widget_repo import InMemoryWidgetRepository
from app.services.rate_limiter import InMemoryTokenBucketRateLimiter
from app.services.widget_service import WidgetTokenService
from app.services.widget_settings import widget_settings


VALID_WIDGET_ID = UUID("9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d")
VALID_ORIGIN = "http://localhost:5500"
SOURCE_IP = "192.0.2.42"

# Patterns that MUST NEVER appear in log output.
UUID_PATTERN = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
IPV4_PATTERN = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}\b")


@pytest.fixture
def captured_logs():
    """Capture all structlog output as a list of JSON dicts during the test."""
    buf = io.StringIO()
    structlog.configure(
        processors=[
            structlog.processors.add_log_level,
            structlog.processors.JSONRenderer(),
        ],
        logger_factory=structlog.PrintLoggerFactory(file=buf),
        cache_logger_on_first_use=False,
    )
    yield buf
    structlog.reset_defaults()


@pytest.fixture
def client(captured_logs):
    service = WidgetTokenService(
        repo=InMemoryWidgetRepository(),
        per_ip_limiter=InMemoryTokenBucketRateLimiter(
            capacity=10000, refill_per_second=10000.0
        ),
        per_widget_limiter=InMemoryTokenBucketRateLimiter(
            capacity=10000, refill_per_second=10000.0
        ),
    )
    app.dependency_overrides[widgets_route.get_widget_token_service] = (
        lambda: service
    )
    yield TestClient(app)
    app.dependency_overrides.pop(widgets_route.get_widget_token_service, None)


def _post(client, *, widget_id=None, origin=VALID_ORIGIN):
    return client.post(
        "/widgets/token",
        headers={"Origin": origin, "X-Forwarded-For": SOURCE_IP},
        json={"widget_id": str(widget_id if widget_id else VALID_WIDGET_ID)},
    )


def test_no_raw_widget_id_or_ip_or_secret_in_logs(captured_logs, client):
    """SC-009: 100 mixed runs produce no raw identifiers or secrets in logs."""
    secret = widget_settings().widget_jwt_secret
    issued_tokens: list[str] = []
    for i in range(100):
        # Half happy-path, half mix of refusal causes.
        if i % 2 == 0:
            res = _post(client)
        elif i % 5 == 1:
            res = _post(client, widget_id=uuid4())
        else:
            res = _post(client, origin="https://attacker.example")
        if res.status_code == 200:
            issued_tokens.append(res.json()["token"])

    log_output = captured_logs.getvalue()
    # Parse each line that looks like JSON.
    log_lines = [
        line.strip() for line in log_output.splitlines() if line.strip()
    ]

    # 1. No JWT signing secret in any line.
    assert secret not in log_output, "JWT signing secret found in logs"

    # 2. No issued token in any line.
    for token in issued_tokens:
        assert token not in log_output, "Raw issued JWT found in logs"

    # 3. No raw VALID_WIDGET_ID UUID in any line.
    raw_widget_id_str = str(VALID_WIDGET_ID)
    assert raw_widget_id_str not in log_output, (
        f"Raw widget_id {raw_widget_id_str} found in logs"
    )

    # 4. No raw source IP in any line.
    assert SOURCE_IP not in log_output, (
        f"Raw source IP {SOURCE_IP} found in logs"
    )

    # 5. Hashed identifiers (64 hex chars) ARE present (positive control).
    hash_pattern = re.compile(r"\b[0-9a-f]{64}\b")
    assert hash_pattern.search(log_output), (
        "Expected to see at least one 64-char hex hash in logs"
    )

    # 6. tenant_id IS present in resolved-widget refusal log records (per data-model.md §3 + Q1 fix).
    has_tenant_id_in_refusal = False
    for line in log_lines:
        try:
            record = json.loads(line)
        except json.JSONDecodeError:
            continue
        if record.get("event") == "widget.token.refused" and "tenant_id" in record:
            has_tenant_id_in_refusal = True
            break
    assert has_tenant_id_in_refusal, (
        "Expected at least one resolved-widget refusal log to include tenant_id"
    )
