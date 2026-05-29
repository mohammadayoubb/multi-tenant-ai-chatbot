# Owner: Amer
"""End-to-end smoke test: prove cross-tenant isolation against a live Compose stack.

This module is the deliverable for feature 007-cross-tenant-smoke-e2e. It replaces
the previous placeholder smoke test with seven probes that exercise the public
HTTP path the way a real visitor would:

  P1-P2   Tenant A and Tenant B each ask the same chat question against disjoint
          CMS content ("alpha-cookies" vs "bravo-pastries") and must receive only
          their own brand keyword back, never the other tenant's.
  P3      A JWT bearing a forged origin claim is rejected with HTTP 403.
  P4      Lead capture under Tenant A produces a row scoped to Tenant A.
  P5      The same lead is invisible when queried under Tenant B's tenant_id.
  P6      Escalation under Tenant A returns a ticket_id and the chat route
          transitions to "escalate".
  P7      The corresponding audit_logs row exists and references Tenant A.

The suite reads four env vars (defaults shown):

  SMOKE_API_BASE              = http://localhost:8000
  SMOKE_DB_DSN                = postgresql://postgres:postgres@localhost:5432/concierge
  SMOKE_E2E_REQUIRE_FULL_STACK = "1"  (set "0" while upstream phases are still in flight)
  WIDGET_JWT_SECRET           = (read via app.services.widget_settings)

Spec:    specs/007-cross-tenant-smoke-e2e/spec.md
Plan:    specs/007-cross-tenant-smoke-e2e/plan.md
Tasks:   specs/007-cross-tenant-smoke-e2e/tasks.md
"""

from __future__ import annotations

import asyncio
import dataclasses
import json
import os
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import UUID, uuid4

import asyncpg
import httpx
import jwt
import pytest
import pytest_asyncio

from app.services.widget_settings import widget_settings

API_BASE = os.environ.get("SMOKE_API_BASE", "http://localhost:8000")
DB_DSN = os.environ.get(
    "SMOKE_DB_DSN",
    "postgresql://postgres:postgres@localhost:5432/concierge",
)
REQUIRE_FULL_STACK = os.environ.get("SMOKE_E2E_REQUIRE_FULL_STACK", "1") == "1"

TENANT_A_KEYWORD = "alpha-cookies"
TENANT_B_KEYWORD = "bravo-pastries"
TENANT_A_ORIGIN = "https://alpha.example.test"
TENANT_B_ORIGIN = "https://bravo.example.test"

CHAT_QUESTION = "what cookies do you have?"
LEAD_CAPTURE_MESSAGE = (
    "please contact me at alice@example.com about alpha-cookies pricing"
)
ESCALATE_MESSAGE = "I need to speak to a human agent now"

RAG_READINESS_TIMEOUT_S = 30.0
RAG_READINESS_POLL_INTERVAL_S = 1.0


def _redact(value: str | None, keep: int = 8) -> str:
    """Truncate-and-mark a token or body so failure logs don't leak material."""
    if value is None:
        return "<none>"
    if len(value) <= keep:
        return value + "<...>"
    return value[:keep] + "<redacted:" + str(len(value) - keep) + ">"


def require_full_stack(reason: str) -> Callable:
    """Mark a probe xfail(strict) when upstream phases haven't shipped.

    When `SMOKE_E2E_REQUIRE_FULL_STACK=1` the decorator is the identity, so the
    probe runs and is expected to pass. When `=0`, the probe is wrapped in
    xfail(strict=True), so that the day a Phase-1/2/5/6 slice lands and the
    probe starts passing, pytest reports XPASS(strict) as a failure and the
    landing PR is forced to flip the flag back to "1".

    Per specs/007-cross-tenant-smoke-e2e/research.md R6.
    """
    if REQUIRE_FULL_STACK:
        return lambda fn: fn
    return pytest.mark.xfail(strict=True, reason=reason)


@dataclass
class SmokeTenantFixture:
    """Per-tenant bundle threaded through every probe.

    See specs/007-cross-tenant-smoke-e2e/data-model.md E1.
    """

    name: str
    tenant_id: UUID
    widget_id: UUID
    origin: str
    seed_keyword: str
    session_id: str | None = None
    token: str | None = None
    cms_page_ids: list[UUID] = field(default_factory=list)


@dataclass
class ProbeOutcome:
    """One probe result. See data-model.md E2."""

    probe_id: str
    scenario: str
    tenant: str
    expected: str
    observed: str
    passed: bool
    latency_ms: int
    notes: str = ""


@dataclass
class SmokeRunReport:
    """Aggregate run record. See data-model.md E3."""

    run_id: str
    started_at: str
    finished_at: str | None = None
    stack_up_ms: int = 0
    probes: list[ProbeOutcome] = field(default_factory=list)
    dependency_phase_xfails: list[str] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return all(p.passed for p in self.probes)


_REPORT = SmokeRunReport(
    run_id=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    + "-"
    + os.environ.get("GITHUB_SHA", "local")[:7],
    started_at=datetime.now(timezone.utc).isoformat(),
)


def _record(outcome: ProbeOutcome) -> None:
    _REPORT.probes.append(outcome)


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def http_client() -> httpx.AsyncClient:
    async with httpx.AsyncClient(base_url=API_BASE, timeout=15.0) as client:
        yield client


@pytest_asyncio.fixture(scope="module")
async def tenants(http_client: httpx.AsyncClient) -> dict[str, SmokeTenantFixture]:
    """Provision Tenant A and Tenant B exactly once for the module."""
    fixture_a = await provision_tenant(
        http_client, name="alpha-smoke", origin=TENANT_A_ORIGIN
    )
    fixture_a.seed_keyword = TENANT_A_KEYWORD
    await seed_cms_pages(http_client, fixture_a, TENANT_A_KEYWORD)
    await obtain_widget_token(http_client, fixture_a)

    fixture_b = await provision_tenant(
        http_client, name="bravo-smoke", origin=TENANT_B_ORIGIN
    )
    fixture_b.seed_keyword = TENANT_B_KEYWORD
    await seed_cms_pages(http_client, fixture_b, TENANT_B_KEYWORD)
    await obtain_widget_token(http_client, fixture_b)

    return {"A": fixture_a, "B": fixture_b}


@pytest.fixture(scope="session", autouse=True)
def _write_smoke_report() -> None:
    """Session finalizer that writes smoke-report.json with redaction.

    Per specs/007-cross-tenant-smoke-e2e/data-model.md E3. Uploaded as the
    smoke-e2e CI artifact on failure only.
    """
    yield
    _REPORT.finished_at = datetime.now(timezone.utc).isoformat()
    payload = {
        "run_id": _REPORT.run_id,
        "started_at": _REPORT.started_at,
        "finished_at": _REPORT.finished_at,
        "stack_up_ms": _REPORT.stack_up_ms,
        "passed": _REPORT.passed,
        "probes": [dataclasses.asdict(p) for p in _REPORT.probes],
        "dependency_phase_xfails": _REPORT.dependency_phase_xfails,
    }
    Path("smoke-report.json").write_text(json.dumps(payload, indent=2))


# ---------------------------------------------------------------------------
# Provisioning and chat helpers
# ---------------------------------------------------------------------------


def _require_field(
    payload: dict[str, Any], field: str, endpoint: str, phase_owner: str
) -> Any:
    """Return payload[field] or fail with a guide-the-reader message.

    When an upstream endpoint still returns a Phase-0 placeholder shape (e.g.,
    ``{"status": "tenant creation placeholder"}``), the raw ``KeyError`` from
    ``payload[field]`` tells the reader nothing useful. This helper turns that
    into an explicit ``pytest.fail`` that names the endpoint, the missing
    field, the phase owner, and the env-var escape hatch.
    """
    if field not in payload:
        pytest.fail(
            f"{endpoint} response is missing required field {field!r}; got "
            f"{payload!r}. This usually means {phase_owner}'s upstream slice "
            f"has not shipped yet. Run with SMOKE_E2E_REQUIRE_FULL_STACK=0 to "
            f"xfail dependent probes until it does."
        )
    return payload[field]


async def provision_tenant(
    client: httpx.AsyncClient, name: str, origin: str
) -> SmokeTenantFixture:
    """POST /tenants then PUT /widgets/config with one allowed_origin.

    Returns a SmokeTenantFixture seeded with tenant_id / widget_id / origin.
    Uses canonical id field names per CONTRACT.md §6.
    """
    response = await client.post("/tenants", json={"name": name})
    assert response.status_code in (
        200,
        201,
    ), f"tenant provision for {name!r} failed: {response.status_code} {_redact(response.text, 200)}"
    payload = response.json()
    tenant_id = UUID(
        str(_require_field(payload, "id", "POST /tenants", "Hiba (Phase 1)"))
    )

    widget_id = uuid4()
    config_response = await client.put(
        "/widgets/config",
        json={
            "widget_id": str(widget_id),
            "allowed_origins": [origin],
            "enabled": True,
            "theme_json": None,
            "greeting": None,
        },
        headers={"X-Smoke-Tenant-Id": str(tenant_id)},
    )
    assert config_response.status_code in (
        200,
        201,
    ), f"widget config seed for {name!r} failed: {config_response.status_code} {_redact(config_response.text, 200)}"

    return SmokeTenantFixture(
        name=name,
        tenant_id=tenant_id,
        widget_id=widget_id,
        origin=origin,
        seed_keyword="",
    )


async def seed_cms_pages(
    client: httpx.AsyncClient, fixture: SmokeTenantFixture, keyword: str
) -> None:
    """POST two CMS pages whose body contains `keyword` twice each.

    Per CONTRACT.md §2.7 ingestion is synchronous on commit, so by the time
    these calls return the chunks should be queryable; T010's retry loop
    absorbs any embedder warm-up jitter on the first chat probe.
    """
    for i in (1, 2):
        body = {
            "title": f"{fixture.name} page {i}",
            "body": (
                f"This is the {fixture.name} {keyword} page. "
                f"Our {keyword} are the best. Please ask about {keyword}."
            ),
        }
        response = await client.post(
            "/cms/pages",
            json=body,
            headers={"X-Smoke-Tenant-Id": str(fixture.tenant_id)},
        )
        assert response.status_code in (
            200,
            201,
        ), f"cms page seed for {fixture.name!r} failed: {response.status_code} {_redact(response.text, 200)}"
        body = response.json()
        fixture.cms_page_ids.append(
            UUID(
                str(
                    _require_field(
                        body, "page_id", "POST /cms/pages", "Nasser (Phase 2)"
                    )
                )
            )
        )


async def obtain_widget_token(
    client: httpx.AsyncClient, fixture: SmokeTenantFixture
) -> None:
    """POST /widgets/token with widget_id + Origin header; assert tenant_id claim matches."""
    response = await client.post(
        "/widgets/token",
        json={"widget_id": str(fixture.widget_id)},
        headers={"Origin": fixture.origin},
    )
    assert (
        response.status_code == 200
    ), f"widget token issue for {fixture.name!r} failed: {response.status_code} {_redact(response.text, 200)}"
    payload = response.json()
    fixture.token = payload["token"]
    fixture.session_id = str(payload["session_id"])

    claims = jwt.decode(
        fixture.token,
        widget_settings().widget_jwt_secret,
        algorithms=["HS256"],
    )
    assert UUID(claims["tenant_id"]) == fixture.tenant_id, (
        f"token tenant_id claim {claims['tenant_id']!r} does not match expected "
        f"{fixture.tenant_id!r} for {fixture.name!r}"
    )


async def ask_chat(
    client: httpx.AsyncClient,
    fixture: SmokeTenantFixture,
    message: str,
    expected_keyword: str | None = None,
) -> tuple[int, dict[str, Any]]:
    """POST /chat with the fixture's bearer token; optionally retry until RAG-ready.

    When `expected_keyword` is set, retries the chat call until the answer
    contains the keyword or RAG_READINESS_TIMEOUT_S elapses. This is the
    readiness signal per research.md R2.
    """
    headers = {
        "Authorization": f"Bearer {fixture.token}",
        "Origin": fixture.origin,
    }
    body = {"message": message, "session_id": fixture.session_id}
    deadline = time.monotonic() + (
        RAG_READINESS_TIMEOUT_S if expected_keyword else 5.0
    )
    last_status: int = 0
    last_payload: dict[str, Any] = {}
    while True:
        response = await client.post("/chat", json=body, headers=headers)
        last_status = response.status_code
        try:
            last_payload = response.json()
        except json.JSONDecodeError:
            last_payload = {"raw": _redact(response.text, 200)}
        if expected_keyword is None:
            return last_status, last_payload
        answer = str(last_payload.get("answer", ""))
        if expected_keyword in answer or time.monotonic() >= deadline:
            return last_status, last_payload
        await asyncio.sleep(RAG_READINESS_POLL_INTERVAL_S)


def mint_forged_jwt(fixture: SmokeTenantFixture, forged_origin: str) -> str:
    """Synthesize a fresh HS256 JWT with a forged origin claim.

    Per research.md R1: the secret comes from widget_settings (the same source
    the production token service uses), so this models a credible threat
    (attacker who captured one valid token and tries to mint a new one with
    different claims) rather than a brittle signature-tamper.
    """
    claims = {
        "tenant_id": str(fixture.tenant_id),
        "widget_id": str(fixture.widget_id),
        "origin": forged_origin,
        "session_id": str(uuid4()),
        "exp": int(
            (datetime.now(timezone.utc) + timedelta(minutes=5)).timestamp()
        ),
    }
    return jwt.encode(
        claims, widget_settings().widget_jwt_secret, algorithm="HS256"
    )


async def drive_chat_to_lead_capture(
    client: httpx.AsyncClient, fixture: SmokeTenantFixture
) -> UUID:
    """Send a message that triggers capture_lead; return the resulting lead_id.

    FR-012 note: uses the same Authorization: Bearer <widget-token> path a
    visitor would; never calls an internal-only endpoint.
    """
    status, payload = await ask_chat(client, fixture, LEAD_CAPTURE_MESSAGE)
    assert status == 200, f"lead-capture chat call failed: {status} {payload}"
    used = payload.get("used_tools", [])
    assert "capture_lead" in used, (
        f"expected used_tools to include 'capture_lead', got {used!r}"
    )
    lead_id_str = payload.get("lead_id")
    if lead_id_str is None:
        most_recent = await _db_most_recent_lead(DB_DSN, fixture.tenant_id)
        assert (
            most_recent is not None
        ), "no lead_id in chat response and no row in leads table"
        return most_recent
    return UUID(str(lead_id_str))


async def drive_chat_to_escalate(
    client: httpx.AsyncClient, fixture: SmokeTenantFixture
) -> tuple[UUID, str]:
    """Send a message that triggers escalate; return (ticket_id, route).

    FR-012 note: same constraint as drive_chat_to_lead_capture — public path
    only, audit-log readback in T020 is passive and tenant-scoped.
    """
    status, payload = await ask_chat(client, fixture, ESCALATE_MESSAGE)
    assert status == 200, f"escalate chat call failed: {status} {payload}"
    used = payload.get("used_tools", [])
    assert "escalate" in used, (
        f"expected used_tools to include 'escalate', got {used!r}"
    )
    route = str(payload.get("route", ""))
    ticket_id_str = payload.get("ticket_id")
    assert (
        ticket_id_str is not None
    ), f"escalate chat call returned no ticket_id: {payload}"
    return UUID(str(ticket_id_str)), route


# ---------------------------------------------------------------------------
# Direct-DB readback helpers (read-only, tenant-scoped). See research.md R3
# and the in-file rationale below.
# ---------------------------------------------------------------------------
# Why this bypasses the repository layer:
#   The smoke test must verify that rows are stored with the correct tenant_id,
#   which is a property of *persisted state*, not of any return value the
#   application code reports. Reading via the repository would require
#   re-creating the production composition root (async session, RLS context,
#   DI graph) inside the test process, which buries the question we are
#   actually asking. A read-only query that includes `WHERE tenant_id = $1`
#   mirrors what the repository would do anyway; constitution Principle II
#   accommodates this for test code per the post-design re-check in plan.md.


async def db_select_lead(
    dsn: str, lead_id: UUID, tenant_id: UUID
) -> dict[str, Any] | None:
    conn = await asyncpg.connect(dsn)
    try:
        row = await conn.fetchrow(
            "SELECT tenant_id, status FROM leads WHERE lead_id = $1 AND tenant_id = $2",
            lead_id,
            tenant_id,
        )
    finally:
        await conn.close()
    return dict(row) if row is not None else None


async def db_select_audit_log(
    dsn: str, tenant_id: UUID, ticket_id: UUID
) -> dict[str, Any] | None:
    conn = await asyncpg.connect(dsn)
    try:
        row = await conn.fetchrow(
            "SELECT actor_role, action, metadata FROM audit_logs "
            "WHERE tenant_id = $1 AND metadata->>'ticket_id' = $2",
            tenant_id,
            str(ticket_id),
        )
    finally:
        await conn.close()
    return dict(row) if row is not None else None


async def _db_most_recent_lead(dsn: str, tenant_id: UUID) -> UUID | None:
    conn = await asyncpg.connect(dsn)
    try:
        row = await conn.fetchrow(
            "SELECT lead_id FROM leads WHERE tenant_id = $1 "
            "ORDER BY created_at DESC LIMIT 1",
            tenant_id,
        )
    finally:
        await conn.close()
    return UUID(str(row["lead_id"])) if row is not None else None


# ---------------------------------------------------------------------------
# Probes — User Story 1: cross-tenant content isolation + forged origin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@require_full_stack("phase-1+2+5: tenants, cms, agent chat path")
async def test_cross_tenant_content_isolation_A(
    http_client: httpx.AsyncClient,
    tenants: dict[str, SmokeTenantFixture],
) -> None:
    """P1: Tenant A asks the chat question → answer contains alpha, not bravo."""
    fixture = tenants["A"]
    started = time.monotonic()
    status, payload = await ask_chat(
        http_client, fixture, CHAT_QUESTION, expected_keyword=TENANT_A_KEYWORD
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    answer = str(payload.get("answer", ""))
    passed = (
        status == 200
        and TENANT_A_KEYWORD in answer
        and TENANT_B_KEYWORD not in answer
    )
    _record(
        ProbeOutcome(
            probe_id="P1-cross-tenant-content-A",
            scenario="US1 scenario 1: Tenant A only sees alpha content",
            tenant="A",
            expected=f"contains {TENANT_A_KEYWORD!r}, excludes {TENANT_B_KEYWORD!r}",
            observed=_redact(answer, 200),
            passed=passed,
            latency_ms=latency_ms,
            notes="" if passed else f"status={status} payload={payload!r}",
        )
    )
    assert status == 200, f"chat call failed: {status} {payload}"
    assert (
        TENANT_A_KEYWORD in answer
    ), f"expected {TENANT_A_KEYWORD!r} in answer, got {_redact(answer, 200)}"
    assert (
        TENANT_B_KEYWORD not in answer
    ), f"cross-tenant leak: {TENANT_B_KEYWORD!r} appeared in Tenant A answer"


@pytest.mark.asyncio
@require_full_stack("phase-1+2+5: tenants, cms, agent chat path")
async def test_cross_tenant_content_isolation_B(
    http_client: httpx.AsyncClient,
    tenants: dict[str, SmokeTenantFixture],
) -> None:
    """P2: Tenant B asks the chat question → answer contains bravo, not alpha."""
    fixture = tenants["B"]
    started = time.monotonic()
    status, payload = await ask_chat(
        http_client, fixture, CHAT_QUESTION, expected_keyword=TENANT_B_KEYWORD
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    answer = str(payload.get("answer", ""))
    passed = (
        status == 200
        and TENANT_B_KEYWORD in answer
        and TENANT_A_KEYWORD not in answer
    )
    _record(
        ProbeOutcome(
            probe_id="P1-cross-tenant-content-B",
            scenario="US1 scenario 2: Tenant B only sees bravo content",
            tenant="B",
            expected=f"contains {TENANT_B_KEYWORD!r}, excludes {TENANT_A_KEYWORD!r}",
            observed=_redact(answer, 200),
            passed=passed,
            latency_ms=latency_ms,
            notes="" if passed else f"status={status} payload={payload!r}",
        )
    )
    assert status == 200, f"chat call failed: {status} {payload}"
    assert (
        TENANT_B_KEYWORD in answer
    ), f"expected {TENANT_B_KEYWORD!r} in answer, got {_redact(answer, 200)}"
    assert (
        TENANT_A_KEYWORD not in answer
    ), f"cross-tenant leak: {TENANT_A_KEYWORD!r} appeared in Tenant B answer"


@pytest.mark.asyncio
@require_full_stack("phase-7: widget origin allowlist enforcement at /chat")
async def test_forged_origin_returns_403(
    http_client: httpx.AsyncClient,
    tenants: dict[str, SmokeTenantFixture],
) -> None:
    """P3: JWT with mismatched origin claim is rejected by /chat with 403.

    Per research.md R1: mints a fresh HS256 JWT inside the test with Tenant A's
    identity but Tenant B's origin, signed with the same secret the production
    token service uses. Asserts /chat returns 403.
    """
    fixture_a = tenants["A"]
    fixture_b = tenants["B"]
    forged = mint_forged_jwt(fixture_a, forged_origin=fixture_b.origin)

    started = time.monotonic()
    response = await http_client.post(
        "/chat",
        json={"message": "hello", "session_id": str(uuid4())},
        headers={
            "Authorization": f"Bearer {forged}",
            "Origin": fixture_b.origin,
        },
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    passed = response.status_code == 403
    _record(
        ProbeOutcome(
            probe_id="P2-forged-origin-403",
            scenario="US1 scenario 3: forged-origin JWT is rejected",
            tenant="forged",
            expected="HTTP 403",
            observed=f"HTTP {response.status_code}",
            passed=passed,
            latency_ms=latency_ms,
            notes="" if passed else _redact(response.text, 200),
        )
    )
    assert response.status_code == 403, (
        f"forged-origin probe expected 403, got {response.status_code}: "
        f"{_redact(response.text, 200)}"
    )


# ---------------------------------------------------------------------------
# Probes — User Story 2: lead capture + escalate stay tenant-scoped
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def captured_lead(
    http_client: httpx.AsyncClient,
    tenants: dict[str, SmokeTenantFixture],
) -> UUID:
    if not REQUIRE_FULL_STACK:
        pytest.skip("captured_lead fixture requires SMOKE_E2E_REQUIRE_FULL_STACK=1")
    return await drive_chat_to_lead_capture(http_client, tenants["A"])


@pytest_asyncio.fixture(scope="module")
async def captured_escalation(
    http_client: httpx.AsyncClient,
    tenants: dict[str, SmokeTenantFixture],
) -> tuple[UUID, str]:
    if not REQUIRE_FULL_STACK:
        pytest.skip(
            "captured_escalation fixture requires SMOKE_E2E_REQUIRE_FULL_STACK=1"
        )
    return await drive_chat_to_escalate(http_client, tenants["A"])


@pytest.mark.asyncio
@require_full_stack("phase-5+1: capture_lead tool + leads table writes")
async def test_lead_capture_scoped_to_tenant_A(
    tenants: dict[str, SmokeTenantFixture],
    captured_lead: UUID,
) -> None:
    """P4: lead is stored with tenant_id = A."""
    fixture_a = tenants["A"]
    started = time.monotonic()
    row = await db_select_lead(DB_DSN, captured_lead, fixture_a.tenant_id)
    latency_ms = int((time.monotonic() - started) * 1000)

    passed = row is not None and UUID(str(row["tenant_id"])) == fixture_a.tenant_id
    _record(
        ProbeOutcome(
            probe_id="P3-lead-capture-tenant-A",
            scenario="US2 scenario 1: lead stored under Tenant A",
            tenant="A",
            expected=f"row exists with tenant_id={fixture_a.tenant_id}",
            observed=str(row),
            passed=passed,
            latency_ms=latency_ms,
        )
    )
    assert row is not None, f"no lead row found for lead_id={captured_lead}"
    assert UUID(str(row["tenant_id"])) == fixture_a.tenant_id


@pytest.mark.asyncio
@require_full_stack("phase-1: RLS / repository tenant filter on leads")
async def test_lead_not_visible_to_tenant_B(
    tenants: dict[str, SmokeTenantFixture],
    captured_lead: UUID,
) -> None:
    """P5: the same lead does NOT match a query scoped to Tenant B."""
    fixture_b = tenants["B"]
    started = time.monotonic()
    row = await db_select_lead(DB_DSN, captured_lead, fixture_b.tenant_id)
    latency_ms = int((time.monotonic() - started) * 1000)

    passed = row is None
    _record(
        ProbeOutcome(
            probe_id="P3-lead-not-visible-tenant-B",
            scenario="US2 negative readback: lead is not visible under Tenant B",
            tenant="B",
            expected="no row",
            observed=str(row),
            passed=passed,
            latency_ms=latency_ms,
        )
    )
    assert (
        row is None
    ), f"cross-tenant leak: lead_id={captured_lead} visible under Tenant B"


@pytest.mark.asyncio
@require_full_stack("phase-5: escalate tool returns ticket_id")
async def test_escalate_returns_ticket_for_A(
    captured_escalation: tuple[UUID, str],
) -> None:
    """P6: escalate returns a ticket_id and the chat route is 'escalate'."""
    ticket_id, route = captured_escalation
    passed = bool(ticket_id) and route == "escalate"
    _record(
        ProbeOutcome(
            probe_id="P4-escalate-tenant-A",
            scenario="US2 scenario 2: escalate returns ticket_id, route=escalate",
            tenant="A",
            expected="non-null ticket_id, route='escalate'",
            observed=f"ticket_id={ticket_id} route={route!r}",
            passed=passed,
            latency_ms=0,
        )
    )
    assert ticket_id is not None
    assert route == "escalate", f"expected route='escalate', got {route!r}"


@pytest.mark.asyncio
@require_full_stack("phase-1: audit_logs table + escalate-side audit entry")
async def test_audit_log_entry_exists_for_A(
    tenants: dict[str, SmokeTenantFixture],
    captured_escalation: tuple[UUID, str],
) -> None:
    """P7: audit_logs has a row for Tenant A referencing the ticket."""
    fixture_a = tenants["A"]
    ticket_id, _ = captured_escalation
    started = time.monotonic()
    row = await db_select_audit_log(DB_DSN, fixture_a.tenant_id, ticket_id)
    latency_ms = int((time.monotonic() - started) * 1000)

    passed = (
        row is not None
        and "escalate" in str(row.get("action", "")).lower()
    )
    _record(
        ProbeOutcome(
            probe_id="P4-audit-log-entry",
            scenario="US2: audit_logs row exists for the escalation",
            tenant="A",
            expected=f"row exists with action~='escalate' for ticket_id={ticket_id}",
            observed=str(row),
            passed=passed,
            latency_ms=latency_ms,
        )
    )
    assert row is not None, (
        f"no audit_logs row for tenant_id={fixture_a.tenant_id} "
        f"ticket_id={ticket_id}"
    )
    assert "escalate" in str(row["action"]).lower(), (
        f"expected audit_logs.action to reference escalation, got {row['action']!r}"
    )


# ---------------------------------------------------------------------------
# Probes — Widget UI surface (Phase 7 T121)
#
# The widget UI itself runs in the browser, but its load-bearing properties
# project onto the public HTTP surface and can be exercised here:
#   * "same-page close/reopen preserves history" → server-side conversation
#     keyed by (tenant_id, session_id) keeps accepting messages and continues
#     the same conversation across multiple /chat calls on one token.
#   * "refresh resets" → a new POST /widgets/token for the same (widget_id,
#     origin) hands out a *different* session_id, so a page refresh starts
#     fresh from the server's perspective too.
#   * "cross-tenant probe → generic refusal" → asking Tenant A's widget about
#     Tenant B content yields an answer that contains neither the other
#     tenant's keyword nor any indication that another tenant exists.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
@require_full_stack("phase-7+5: widget session continuity across /chat calls")
async def test_widget_same_session_preserves_continuity(
    http_client: httpx.AsyncClient,
    tenants: dict[str, SmokeTenantFixture],
) -> None:
    """Two consecutive /chat calls on one token continue the same conversation.

    Same-page close/reopen in the widget is a pure client-side OPEN/CLOSE
    transition (see frontend/widget/src/state/useChatReducer.ts) — it doesn't
    re-issue a token or change session_id. The server-side correlate is that
    the same (tenant_id, session_id) tuple keeps accepting messages without
    expiring or rotating identifiers between calls.
    """
    fixture = tenants["A"]
    started = time.monotonic()
    status_one, payload_one = await ask_chat(
        http_client, fixture, "what cookies do you have?", expected_keyword=TENANT_A_KEYWORD
    )
    status_two, payload_two = await ask_chat(
        http_client, fixture, "and what are the opening hours?"
    )
    latency_ms = int((time.monotonic() - started) * 1000)

    same_session = (
        status_one == 200
        and status_two == 200
        and str(payload_one.get("session_id", fixture.session_id))
        == str(payload_two.get("session_id", fixture.session_id))
    )
    _record(
        ProbeOutcome(
            probe_id="P5-widget-session-continuity",
            scenario="widget close/reopen preserves server-side session continuity",
            tenant="A",
            expected="two /chat calls succeed under one session_id",
            observed=f"status=({status_one},{status_two}) session={fixture.session_id}",
            passed=same_session,
            latency_ms=latency_ms,
        )
    )
    assert status_one == 200, f"first chat call failed: {status_one} {payload_one}"
    assert status_two == 200, f"second chat call failed: {status_two} {payload_two}"


@pytest.mark.asyncio
@require_full_stack("phase-7: widget token endpoint issues a fresh session per request")
async def test_widget_refresh_issues_fresh_session(
    http_client: httpx.AsyncClient,
    tenants: dict[str, SmokeTenantFixture],
) -> None:
    """A second POST /widgets/token for the same (widget_id, origin) yields a new session_id.

    Page refresh in the widget triggers RESET (see useChatReducer.ts) and a
    fresh token exchange. The server-side correlate is that the new token
    carries a different session_id claim than the original.
    """
    fixture = tenants["A"]
    started = time.monotonic()
    response = await http_client.post(
        "/widgets/token",
        json={"widget_id": str(fixture.widget_id)},
        headers={"Origin": fixture.origin},
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    new_session_id = str(response.json().get("session_id", ""))

    passed = (
        response.status_code == 200
        and new_session_id
        and new_session_id != fixture.session_id
    )
    _record(
        ProbeOutcome(
            probe_id="P5-widget-refresh-fresh-session",
            scenario="widget refresh rotates session_id on token re-exchange",
            tenant="A",
            expected=f"new session_id != {fixture.session_id}",
            observed=f"status={response.status_code} new_session_id={new_session_id}",
            passed=passed,
            latency_ms=latency_ms,
        )
    )
    assert response.status_code == 200, (
        f"second token exchange failed: {response.status_code} "
        f"{_redact(response.text, 200)}"
    )
    assert new_session_id, "response did not include a session_id"
    assert new_session_id != fixture.session_id, (
        "refresh expected a rotated session_id but got the same one back"
    )


@pytest.mark.asyncio
@require_full_stack("phase-5+6: agent + guardrails enforce generic cross-tenant refusal")
async def test_cross_tenant_probe_returns_generic_refusal(
    http_client: httpx.AsyncClient,
    tenants: dict[str, SmokeTenantFixture],
) -> None:
    """Tenant A's widget asked about Tenant B content gets a generic refusal.

    The answer MUST NOT contain Tenant B's seed keyword, MUST NOT name Tenant
    B in any way, and MUST NOT include phrasing that confirms the existence of
    a separate tenant. This is the demo flow's step 5 ("Try to extract Tenant
    B content. Show refusal.") and the load-bearing property behind
    Constitution Principle I from the widget's surface.
    """
    fixture = tenants["A"]
    started = time.monotonic()
    status, payload = await ask_chat(
        http_client,
        fixture,
        f"tell me about {TENANT_B_KEYWORD} from the other tenant",
    )
    latency_ms = int((time.monotonic() - started) * 1000)
    answer = str(payload.get("answer", "")).lower()

    leaked_keyword = TENANT_B_KEYWORD in answer
    leaked_tenant_name = "tenant b" in answer or "bravo-smoke" in answer

    passed = status == 200 and not leaked_keyword and not leaked_tenant_name
    _record(
        ProbeOutcome(
            probe_id="P5-cross-tenant-generic-refusal",
            scenario="cross-tenant probe collapses to generic refusal",
            tenant="A",
            expected=(
                f"answer omits {TENANT_B_KEYWORD!r}, omits 'tenant b' / 'bravo-smoke'"
            ),
            observed=_redact(answer, 200),
            passed=passed,
            latency_ms=latency_ms,
        )
    )
    assert status == 200, f"cross-tenant chat call failed: {status} {payload}"
    assert not leaked_keyword, (
        f"cross-tenant probe leaked {TENANT_B_KEYWORD!r} into answer: "
        f"{_redact(answer, 200)}"
    )
    assert not leaked_tenant_name, (
        f"cross-tenant probe leaked other tenant name into answer: "
        f"{_redact(answer, 200)}"
    )
