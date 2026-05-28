# Owner: Amer
"""End-to-end tests for the admin-JWT read endpoints (BLOCKED.md H5/H6/N8/N9).

  - GET /tenants/{tid}/audit-logs
  - GET /tenants/{tid}/usage
  - GET /cms/pages
  - POST /cms/pages
  - GET /leads

All five are gated by `require_admin_session`. They share two security
invariants the tests assert explicitly:

  1. No admin JWT  →  403 (regardless of CONCIERGE_ENV).
  2. Cross-tenant path  →  403 (a tenant_admin cannot read another tenant's
     data even when their JWT is otherwise valid).

Tests run against in-memory fakes for the repos so they don't need a real
Postgres. The full HTTP request/response cycle still goes through
FastAPI's router stack — auth, validation, and serialization are all
exercised end-to-end.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.admin_auth as admin_auth_route
import app.api.routes.cms as cms_route
import app.api.routes.leads as leads_route
from app.api.deps import get_tenant_repository
from app.db.session import get_session
from app.infra.password import hash_password
from app.main import app


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


TENANT_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


@dataclass
class _FakeAdminUser:
    id: UUID
    tenant_id: UUID
    email: str
    password_hash: str
    role: str = "tenant_admin"
    full_name: str | None = None
    status: str = "active"


class _UserRepo:
    def __init__(self, users: list[_FakeAdminUser]) -> None:
        self._by_email = {u.email: u for u in users}

    async def get_by_email(self, email: str):
        return self._by_email.get(email)


@dataclass
class _FakeAuditRow:
    id: UUID
    tenant_id: UUID
    actor_id: str | None
    actor_role: str
    action: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


@dataclass
class _FakeLead:
    id: UUID
    tenant_id: UUID
    name: str | None
    contact: str | None
    intent: str
    status: str = "captured"
    quality_score: float | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class _FakeCmsPage:
    id: UUID
    tenant_id: UUID
    title: str
    slug: str
    body: str
    source_url: str | None
    status: str
    created_by: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class _TenantRepo:
    def __init__(
        self,
        *,
        audit_rows: list[_FakeAuditRow],
        rollups: dict[UUID, dict[str, Any]],
    ) -> None:
        self._audit = audit_rows
        self._rollups = rollups

    async def list_audit_logs(self, tenant_id: UUID) -> list[_FakeAuditRow]:
        return [r for r in self._audit if r.tenant_id == tenant_id]

    async def usage_rollup(self, tenant_id: UUID, *, since: datetime) -> dict[str, Any]:
        return self._rollups.get(tenant_id, _empty_rollup())


def _empty_rollup() -> dict[str, Any]:
    return {
        "total_tokens": 0,
        "total_cost_usd": 0.0,
        "by_feature": {},
        "daily_cost_usd": [],
    }


class _LeadRepoFake:
    def __init__(self, rows: list[_FakeLead]) -> None:
        self._rows = rows

    async def list_by_tenant(self, tenant_id: UUID, *, limit: int = 100):
        return [r for r in self._rows if r.tenant_id == tenant_id][:limit]


class _CmsRepoFake:
    def __init__(self, rows: list[_FakeCmsPage]) -> None:
        self.rows = list(rows)

    async def list_pages(self, tenant_id: UUID):
        return [p for p in self.rows if p.tenant_id == tenant_id]

    async def create(
        self,
        *,
        tenant_id: UUID,
        title: str,
        slug: str,
        body: str,
        source_url: str | None = None,
        status: str = "published",
        created_by: str | None = None,
    ):
        page = _FakeCmsPage(
            id=uuid4(),
            tenant_id=tenant_id,
            title=title,
            slug=slug,
            body=body,
            source_url=source_url,
            status=status,
            created_by=created_by,
        )
        self.rows.append(page)
        return page


# ---------------------------------------------------------------------------
# Shared fixture
# ---------------------------------------------------------------------------


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    """Set up two tenants worth of seeded data + an admin JWT for TENANT_A."""
    monkeypatch.setenv("CONCIERGE_ENV", "prod")  # close dev-header fallback

    admin_user_repo = _UserRepo(
        [
            _FakeAdminUser(
                id=uuid4(),
                tenant_id=TENANT_A,
                email="alice@a.example",
                password_hash=hash_password("AlicePw1"),
                role="tenant_admin",
            )
        ]
    )

    audit_rows = [
        _FakeAuditRow(
            id=uuid4(),
            tenant_id=TENANT_A,
            actor_id="alice@a.example",
            actor_role="tenant_admin",
            action="widget.origin_added",
            metadata_json={"origin": "https://a.example"},
            created_at=datetime.now(UTC) - timedelta(days=1),
            updated_at=datetime.now(UTC) - timedelta(days=1),
        ),
        # Tenant B row — must NOT show up in tenant A's response.
        _FakeAuditRow(
            id=uuid4(),
            tenant_id=TENANT_B,
            actor_id="bob@b.example",
            actor_role="tenant_admin",
            action="cms.page_created",
            metadata_json={},
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        ),
    ]

    rollups = {
        TENANT_A: {
            "total_tokens": 1500,
            "total_cost_usd": 1.25,
            "by_feature": {"chat": {"tokens": 1500, "cost_usd": 1.25}},
            "daily_cost_usd": [{"date": "2026-05-27", "cost_usd": 1.25}],
        }
    }

    leads = [
        _FakeLead(
            id=uuid4(),
            tenant_id=TENANT_A,
            name="Lead A1",
            contact="lead-a1@a.example",
            intent="pricing",
        ),
        _FakeLead(
            id=uuid4(),
            tenant_id=TENANT_B,
            name="Lead B1",
            contact="lead-b1@b.example",
            intent="demo",
        ),
    ]

    cms_pages = [
        _FakeCmsPage(
            id=uuid4(),
            tenant_id=TENANT_A,
            title="Welcome",
            slug="welcome",
            body="hi",
            source_url=None,
            status="published",
        ),
        _FakeCmsPage(
            id=uuid4(),
            tenant_id=TENANT_B,
            title="Tenant B page",
            slug="b-page",
            body="b",
            source_url=None,
            status="published",
        ),
    ]
    cms_repo_fake = _CmsRepoFake(cms_pages)

    tenant_repo = _TenantRepo(audit_rows=audit_rows, rollups=rollups)
    lead_repo = _LeadRepoFake(leads)

    # Patch the per-route repository constructors (admin_auth/cms/leads use
    # local imports). The tenants routes consume get_tenant_repository via
    # `app.api.deps`, so for those we use FastAPI's dependency_overrides.
    monkeypatch.setattr(admin_auth_route, "AdminUserRepository", lambda _s: admin_user_repo)
    monkeypatch.setattr(leads_route, "LeadRepository", lambda _s: lead_repo)
    monkeypatch.setattr(cms_route, "CmsRepository", lambda _s: cms_repo_fake)

    async def _no_db():
        yield None

    async def _override_tenant_repo():
        return tenant_repo

    app.dependency_overrides[get_session] = _no_db
    app.dependency_overrides[get_tenant_repository] = _override_tenant_repo
    try:
        with TestClient(app) as tc:
            yield tc, cms_repo_fake
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_tenant_repository, None)


def _login(tc: TestClient, email: str, password: str) -> str:
    resp = tc.post("/admin/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


# ---------------------------------------------------------------------------
# H5  GET /tenants/{tid}/audit-logs
# ---------------------------------------------------------------------------


def test_audit_logs_returns_own_tenant_rows(client) -> None:
    tc, _ = client
    token = _login(tc, "alice@a.example", "AlicePw1")
    resp = tc.get(
        f"/tenants/{TENANT_A}/audit-logs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["action"] == "widget.origin_added"


def test_audit_logs_rejects_cross_tenant_path(client) -> None:
    """Alice (tenant A) cannot read tenant B's audit log even with a valid JWT."""
    tc, _ = client
    token = _login(tc, "alice@a.example", "AlicePw1")
    resp = tc.get(
        f"/tenants/{TENANT_B}/audit-logs",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_audit_logs_without_jwt_in_prod_mode_returns_403(client) -> None:
    tc, _ = client
    resp = tc.get(f"/tenants/{TENANT_A}/audit-logs")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# H6  GET /tenants/{tid}/usage
# ---------------------------------------------------------------------------


def test_usage_rollup_returns_dashboard_shape(client) -> None:
    tc, _ = client
    token = _login(tc, "alice@a.example", "AlicePw1")
    resp = tc.get(
        f"/tenants/{TENANT_A}/usage",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["total_tokens"] == 1500
    assert body["total_cost_usd"] == 1.25
    assert body["by_feature"]["chat"]["tokens"] == 1500
    assert body["daily_cost_usd"][0]["date"] == "2026-05-27"


def test_usage_rollup_rejects_cross_tenant_path(client) -> None:
    tc, _ = client
    token = _login(tc, "alice@a.example", "AlicePw1")
    resp = tc.get(
        f"/tenants/{TENANT_B}/usage",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# N8  GET /leads
# ---------------------------------------------------------------------------


def test_leads_lists_only_caller_tenant(client) -> None:
    tc, _ = client
    token = _login(tc, "alice@a.example", "AlicePw1")
    resp = tc.get("/leads", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["name"] == "Lead A1"
    assert body[0]["contact"] == "lead-a1@a.example"


def test_leads_without_jwt_returns_403(client) -> None:
    tc, _ = client
    resp = tc.get("/leads")
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# N9 / N1  GET + POST /cms/pages
# ---------------------------------------------------------------------------


def test_cms_pages_list_returns_only_caller_tenant(client) -> None:
    tc, _ = client
    token = _login(tc, "alice@a.example", "AlicePw1")
    resp = tc.get("/cms/pages", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) == 1
    assert body[0]["slug"] == "welcome"


def test_cms_pages_create_uses_jwt_tenant_id_not_body(client) -> None:
    """Body cannot override tenant_id (the schema doesn't even accept it)."""
    tc, repo = client
    token = _login(tc, "alice@a.example", "AlicePw1")
    resp = tc.post(
        "/cms/pages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Pricing",
            "slug": "pricing",
            "body": "All plans.",
            "status": "published",
        },
    )
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["slug"] == "pricing"
    # Verify the persisted row is scoped to TENANT_A (alice's tenant).
    matching = [p for p in repo.rows if p.slug == "pricing"]
    assert len(matching) == 1
    assert matching[0].tenant_id == TENANT_A
    assert matching[0].created_by == "alice@a.example"


def test_cms_pages_create_rejects_extra_tenant_id_field(client) -> None:
    """Even if the body smuggles a tenant_id field, validation rejects it (extra=forbid)."""
    tc, _ = client
    token = _login(tc, "alice@a.example", "AlicePw1")
    resp = tc.post(
        "/cms/pages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "x",
            "slug": "x",
            "body": "x",
            "tenant_id": str(TENANT_B),  # forbidden extra
        },
    )
    assert resp.status_code == 422
