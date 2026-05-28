# Owner: Amer
"""Security tests for the widget token exchange endpoint.

Covers spec.md FR-001..FR-019 (gating + refusals + rate limits + lifetime)
and success criteria SC-001, SC-002, SC-003, SC-007.
"""

from __future__ import annotations

import time
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

import app.api.routes.widgets as widgets_route
from app.domain.widget import WidgetConfigDomain
from app.main import app
from app.repositories.widget_repo import InMemoryWidgetRepository
from app.services.rate_limiter import InMemoryTokenBucketRateLimiter
from app.services.widget_service import WidgetTokenService
from app.services.widget_settings import widget_settings


VALID_WIDGET_ID = UUID("9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d")
VALID_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
ROW_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
VALID_ORIGIN = "http://localhost:5500"


def _make_service(
    *,
    repo: InMemoryWidgetRepository | None = None,
    per_ip_capacity: int = 10000,
    per_widget_capacity: int = 10000,
) -> tuple[WidgetTokenService, InMemoryWidgetRepository]:
    repo = repo or InMemoryWidgetRepository()
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
    return service, repo


@pytest.fixture
def service_factory():
    """Yield a callable that swaps in a fresh service with custom limits.

    Tests that do NOT exercise rate-limit behavior should use the default
    (wide-open) limiter capacity. Tests that DO exercise rate-limit behavior
    call this with a low capacity.
    """
    repos: list[InMemoryWidgetRepository] = []

    def factory(
        *,
        per_ip_capacity: int = 10000,
        per_widget_capacity: int = 10000,
    ) -> InMemoryWidgetRepository:
        service, repo = _make_service(
            per_ip_capacity=per_ip_capacity,
            per_widget_capacity=per_widget_capacity,
        )
        app.dependency_overrides[widgets_route.get_widget_token_service] = (
            lambda: service
        )
        repos.append(repo)
        return repo

    yield factory
    app.dependency_overrides.pop(widgets_route.get_widget_token_service, None)


@pytest.fixture
def repo(service_factory) -> InMemoryWidgetRepository:
    return service_factory()


@pytest.fixture
def client():
    return TestClient(app)


def _post(client, *, widget_id: UUID | None = None, origin: str | None = VALID_ORIGIN):
    headers = {}
    if origin is not None:
        headers["Origin"] = origin
    return client.post(
        "/widgets/token",
        headers=headers,
        json={"widget_id": str(widget_id if widget_id else VALID_WIDGET_ID)},
    )


# ---------------- US1: Happy path ----------------


def test_happy_path_returns_signed_token(repo, client):
    res = _post(client)
    assert res.status_code == 200
    body = res.json()
    assert set(body.keys()) == {"token", "expires_in", "session_id"}
    assert body["expires_in"] == widget_settings().widget_token_ttl_seconds

    claims = jwt.decode(
        body["token"],
        widget_settings().widget_jwt_secret,
        algorithms=["HS256"],
    )
    assert claims["tenant_id"] == str(VALID_TENANT_ID)
    assert claims["widget_id"] == str(VALID_WIDGET_ID)
    assert claims["origin"] == VALID_ORIGIN
    assert claims["session_id"] == body["session_id"]
    assert claims["exp"] == claims["iat"] + widget_settings().widget_token_ttl_seconds


def test_success_response_headers(repo, client):
    res = _post(client)
    assert res.status_code == 200
    assert res.headers["Cache-Control"] == "no-store"
    assert res.headers["Content-Type"].startswith("application/json")


# ---------------- US2: Refusals byte-identical ----------------

REFUSAL_BODY = b'{"error":"widget_unavailable"}'


def _suspended_row() -> WidgetConfigDomain:
    return WidgetConfigDomain(
        id=ROW_ID,
        tenant_id=VALID_TENANT_ID,
        widget_id=VALID_WIDGET_ID,
        allowed_origins=[VALID_ORIGIN],
        enabled=True,
        tenant_status="suspended",
    )


def _disabled_row() -> WidgetConfigDomain:
    return WidgetConfigDomain(
        id=ROW_ID,
        tenant_id=VALID_TENANT_ID,
        widget_id=VALID_WIDGET_ID,
        allowed_origins=[VALID_ORIGIN],
        enabled=False,
        tenant_status="active",
    )


def test_unknown_widget_returns_403(repo, client):
    res = _post(client, widget_id=uuid4())
    assert res.status_code == 403
    assert res.content == REFUSAL_BODY


def test_origin_not_allowlisted_returns_403(repo, client):
    res = _post(client, origin="https://attacker.example")
    assert res.status_code == 403
    assert res.content == REFUSAL_BODY


def test_widget_disabled_returns_403(repo, client):
    repo.upsert(_disabled_row())
    res = _post(client)
    assert res.status_code == 403
    assert res.content == REFUSAL_BODY


def test_tenant_suspended_returns_403(repo, client):
    repo.upsert(_suspended_row())
    res = _post(client)
    assert res.status_code == 403
    assert res.content == REFUSAL_BODY


def test_all_refusal_causes_byte_identical(service_factory, client):
    """SC-002: refusal responses byte-identical across every cause."""
    # unknown_widget
    repo = service_factory()
    unknown = _post(client, widget_id=uuid4())

    # origin_not_allowlisted (default fixture; bad origin)
    repo = service_factory()
    wrong_origin = _post(client, origin="https://attacker.example")

    # widget_disabled
    repo = service_factory()
    repo.upsert(_disabled_row())
    disabled = _post(client)

    # tenant_not_active
    repo = service_factory()
    repo.upsert(_suspended_row())
    suspended = _post(client)

    bodies = {
        "unknown": unknown.content,
        "wrong_origin": wrong_origin.content,
        "disabled": disabled.content,
        "suspended": suspended.content,
    }
    statuses = {k: r.status_code for k, r in {
        "unknown": unknown,
        "wrong_origin": wrong_origin,
        "disabled": disabled,
        "suspended": suspended,
    }.items()}
    assert all(s == 403 for s in statuses.values()), statuses
    distinct_bodies = set(bodies.values())
    assert len(distinct_bodies) == 1, (
        f"Refusal responses MUST be byte-identical, got distinct bodies: {bodies}"
    )


def test_refusal_response_headers(repo, client):
    res = _post(client, widget_id=uuid4())
    assert res.status_code == 403
    assert res.headers["Cache-Control"] == "no-store"
    assert res.headers["Content-Type"].startswith("application/json")


def test_missing_origin_returns_400(repo, client):
    res = client.post(
        "/widgets/token",
        json={"widget_id": str(VALID_WIDGET_ID)},
    )
    assert res.status_code == 400
    assert res.content == b'{"error":"bad_request"}'


def test_malformed_widget_id_returns_400(repo, client):
    res = client.post(
        "/widgets/token",
        headers={"Origin": VALID_ORIGIN},
        json={"widget_id": "not-a-uuid"},
    )
    assert res.status_code == 400
    assert res.content == b'{"error":"bad_request"}'


# ---------------- US2: Rate limits ----------------


def test_per_ip_rate_limit_returns_byte_identical_403(service_factory, client):
    service_factory(per_ip_capacity=2)
    # First two pass.
    assert _post(client).status_code == 200
    assert _post(client).status_code == 200
    # Third hits the per-IP limit.
    rate_limited = _post(client)
    assert rate_limited.status_code == 403
    assert rate_limited.content == REFUSAL_BODY


def test_per_widget_rate_limit_returns_byte_identical_403(service_factory, client):
    service_factory(per_widget_capacity=2)
    assert _post(client).status_code == 200
    assert _post(client).status_code == 200
    rate_limited = _post(client)
    assert rate_limited.status_code == 403
    assert rate_limited.content == REFUSAL_BODY


# ---------------- US2: Timing discipline (FR-008a) ----------------


def test_unknown_widget_and_origin_mismatch_have_similar_latency(repo, client):
    """FR-008a: both paths must run the widget lookup; their medians should be close."""
    samples_unknown: list[float] = []
    samples_wrong_origin: list[float] = []
    for _ in range(20):
        t0 = time.perf_counter()
        _post(client, widget_id=uuid4())
        samples_unknown.append(time.perf_counter() - t0)
        t0 = time.perf_counter()
        _post(client, origin="https://attacker.example")
        samples_wrong_origin.append(time.perf_counter() - t0)
    samples_unknown.sort()
    samples_wrong_origin.sort()
    median_unknown = samples_unknown[len(samples_unknown) // 2]
    median_wrong = samples_wrong_origin[len(samples_wrong_origin) // 2]
    # Tolerance: 30ms — generous because in-memory lookup is fast and noise
    # dominates. The test guards against gross signals (multiple-x differences).
    delta_ms = abs(median_unknown - median_wrong) * 1000
    assert delta_ms < 30, (
        f"Refusal-path latency divergence too large: {delta_ms:.2f} ms "
        f"(unknown median {median_unknown*1000:.2f}ms vs "
        f"wrong-origin median {median_wrong*1000:.2f}ms)"
    )


# ---------------- US3: Lifetime + freshness ----------------


def test_session_id_is_fresh_per_issuance(repo, client):
    body_a = _post(client).json()
    body_b = _post(client).json()
    assert body_a["session_id"] != body_b["session_id"]


def test_token_ttl_matches_settings(repo, client):
    body = _post(client).json()
    claims = jwt.decode(
        body["token"],
        widget_settings().widget_jwt_secret,
        algorithms=["HS256"],
    )
    assert claims["exp"] - claims["iat"] == widget_settings().widget_token_ttl_seconds


# ---------------- T046: Latency sanity (SC-003) ----------------


def test_happy_path_p95_under_50ms(repo, client):
    """SC-003 sanity guard: server-side p95 < 50 ms on in-memory backend."""
    samples: list[float] = []
    for _ in range(100):
        t0 = time.perf_counter()
        res = _post(client)
        samples.append(time.perf_counter() - t0)
        assert res.status_code == 200
    samples.sort()
    p95 = samples[int(0.95 * len(samples))]
    assert p95 * 1000 < 50, f"happy-path p95 = {p95*1000:.2f}ms (target < 50ms)"


# ---------------- T045 BLOCKED: expired-token rejection by /chat ----------------


@pytest.mark.skip(reason="blocked on Hiba widget-token JWT verifier in app/api/deps.py")
def test_expired_token_rejected_by_chat() -> None:
    """Asserts /chat returns 401 for expired tokens; requires Hiba's real verifier."""
    raise AssertionError("placeholder; wired when Hiba's verifier ships")
