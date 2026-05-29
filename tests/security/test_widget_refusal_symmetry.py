# Owner: Amer
"""T045a — anti-enumeration regression for SC-008.

Every refusal cause on POST /widgets/token MUST collapse to the same
byte-identical body ``{"error":"widget_unavailable"}`` with status 403. The
existing test_widget_token.py covers four causes today; this file pins the
contract down with a dedicated negative sweep that future endpoint owners
must not break.
"""

from __future__ import annotations

from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.widgets as widgets_route
from app.domain.widget import WidgetConfigDomain
from app.main import app
from app.repositories.widget_repo import InMemoryWidgetRepository
from app.services.rate_limiter import InMemoryTokenBucketRateLimiter
from app.services.widget_service import WidgetTokenService

REFUSAL_BODY = b'{"error":"widget_unavailable"}'
VALID_WIDGET_ID = UUID("9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d")
VALID_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
VALID_ORIGIN = "http://localhost:5500"
ROW_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


def _install_service(
    *,
    per_ip_capacity: int = 10_000,
    per_widget_capacity: int = 10_000,
) -> InMemoryWidgetRepository:
    repo = InMemoryWidgetRepository()
    service = WidgetTokenService(
        repo=repo,
        per_ip_limiter=InMemoryTokenBucketRateLimiter(
            capacity=per_ip_capacity, refill_per_second=float(per_ip_capacity)
        ),
        per_widget_limiter=InMemoryTokenBucketRateLimiter(
            capacity=per_widget_capacity,
            refill_per_second=float(per_widget_capacity),
        ),
    )
    app.dependency_overrides[widgets_route.get_widget_token_service] = (
        lambda: service
    )
    return repo


@pytest.fixture
def client():
    yield TestClient(app)
    app.dependency_overrides.pop(widgets_route.get_widget_token_service, None)


def _post(client: TestClient, *, widget_id: UUID, origin: str):
    return client.post(
        "/widgets/token",
        headers={"Origin": origin},
        json={"widget_id": str(widget_id)},
    )


def _suspended_row() -> WidgetConfigDomain:
    return WidgetConfigDomain(
        id=ROW_ID,
        tenant_id=VALID_TENANT_ID,
        widget_id=VALID_WIDGET_ID,
        allowed_origins=[VALID_ORIGIN],
        enabled=True,
        tenant_status="suspended",
    )


def test_refusal_body_is_byte_identical_across_all_known_causes(client: TestClient):
    """SC-008 anti-enumeration: every 403 path returns the same bytes."""
    bodies: list[bytes] = []

    # Cause 1: origin mismatch.
    _install_service()
    res = _post(client, widget_id=VALID_WIDGET_ID, origin="https://attacker.example")
    assert res.status_code == 403
    bodies.append(res.content)

    # Cause 2: unknown widget_id.
    _install_service()
    res = _post(client, widget_id=uuid4(), origin=VALID_ORIGIN)
    assert res.status_code == 403
    bodies.append(res.content)

    # Cause 3: suspended tenant.
    repo = _install_service()
    repo.upsert(_suspended_row())
    res = _post(client, widget_id=VALID_WIDGET_ID, origin=VALID_ORIGIN)
    assert res.status_code == 403
    bodies.append(res.content)

    # Cause 4: rate-limited (per-IP bucket exhausted).
    _install_service(per_ip_capacity=1)
    _post(client, widget_id=VALID_WIDGET_ID, origin=VALID_ORIGIN)  # consumes the bucket
    res = _post(client, widget_id=VALID_WIDGET_ID, origin=VALID_ORIGIN)
    assert res.status_code == 403
    bodies.append(res.content)

    distinct = set(bodies)
    assert distinct == {REFUSAL_BODY}, (
        f"Refusal bodies diverged across causes: {bodies}"
    )


def test_refusal_headers_do_not_leak_cause(client: TestClient):
    """Headers must not differ by refusal cause either."""
    _install_service()
    wrong_origin = _post(
        client, widget_id=VALID_WIDGET_ID, origin="https://attacker.example"
    )
    _install_service()
    unknown_widget = _post(client, widget_id=uuid4(), origin=VALID_ORIGIN)

    # Compare a tight set of response headers that callers can observe.
    keys = ("Content-Type", "Cache-Control")
    a = {k: wrong_origin.headers.get(k) for k in keys}
    b = {k: unknown_widget.headers.get(k) for k in keys}
    assert a == b, f"Refusal headers diverged: {a} vs {b}"
