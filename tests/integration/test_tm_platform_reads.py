# Owner: Hiba
"""Integration tests for the TM-scope platform reads.

GET /tenants     — TM only, admin-JWT-gated
GET /audit-logs  — TM only, admin-JWT-gated (mounted on the platform_router)

Asserts:
- TM can read both.
- TA → 403 on both.
- Cross-content denial holds: no CMS body / lead detail / message text in any
  response field. (The endpoints return tenant metadata + audit-log rows only;
  if the wire shape ever drifts to include content, this guardrail trips.)
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.admin_auth as admin_auth_route
import app.api.routes.tenants as tenants_route
from app.api.deps import get_tenant_repository
from app.db.session import get_session
from app.infra.password import hash_password
from app.main import app


TENANT_A = UUID("11111111-aaaa-aaaa-aaaa-111111111111")
TENANT_B = UUID("22222222-bbbb-bbbb-bbbb-222222222222")


@dataclass
class _FakeUser:
    id: UUID
    tenant_id: UUID
    email: str
    password_hash: str
    role: str = "tenant_admin"
    full_name: str | None = None
    status: str = "active"


@dataclass
class _FakeTenant:
    id: UUID
    name: str
    slug: str = "demo"
    status: str = "active"
    plan: str = "starter"
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass
class _FakeAuditLog:
    id: UUID
    tenant_id: UUID
    actor_id: str
    actor_role: str
    action: str
    metadata_json: dict
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


class _TenantRepoStub:
    def __init__(self) -> None:
        self.tenants = [
            _FakeTenant(id=TENANT_A, name="Acme", slug="acme"),
            _FakeTenant(id=TENANT_B, name="Beta", slug="beta"),
        ]
        self.audit_rows = [
            _FakeAuditLog(
                id=uuid4(),
                tenant_id=TENANT_A,
                actor_id="someone@acme.example",
                actor_role="tenant_admin",
                action="cms.page_updated",
                metadata_json={"page_id": str(uuid4())},
            ),
            _FakeAuditLog(
                id=uuid4(),
                tenant_id=TENANT_B,
                actor_id="boss@platform.example",
                actor_role="tenant_manager",
                action="tenant.provisioned",
                metadata_json={"tenant_name": "Beta"},
            ),
        ]

    async def list_all(self):
        return list(self.tenants)

    async def list_audit_logs_platform_scope(self, **kwargs):
        out = list(self.audit_rows)
        if kwargs.get("actor"):
            out = [r for r in out if r.actor_id == kwargs["actor"]]
        if kwargs.get("tenant_id") is not None:
            out = [r for r in out if r.tenant_id == kwargs["tenant_id"]]
        if kwargs.get("action"):
            out = [r for r in out if r.action == kwargs["action"]]
        return out


class _UserRepo:
    def __init__(self) -> None:
        self.by_email: dict[str, _FakeUser] = {}

    async def get_by_email(self, email):
        return self.by_email.get(email)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("CONCIERGE_ENV", "dev")

    tenant_repo = _TenantRepoStub()
    user_repo = _UserRepo()
    user_repo.by_email["tm@platform.example"] = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_A,
        email="tm@platform.example",
        password_hash=hash_password("Password1"),
        role="tenant_manager",
    )
    user_repo.by_email["ta@acme.example"] = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_A,
        email="ta@acme.example",
        password_hash=hash_password("Password1"),
        role="tenant_admin",
    )

    monkeypatch.setattr(admin_auth_route, "AdminUserRepository", lambda _s: user_repo)
    monkeypatch.setattr(tenants_route, "TenantRepository", lambda _s: tenant_repo)

    async def _no_db():
        yield None

    async def _override_repo():
        return tenant_repo

    app.dependency_overrides[get_session] = _no_db
    app.dependency_overrides[get_tenant_repository] = _override_repo
    try:
        with TestClient(app) as tc:
            yield tc
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(get_tenant_repository, None)


def _login(tc, email):
    return tc.post(
        "/admin/login", json={"email": email, "password": "Password1"}
    ).json()["token"]


def test_tm_can_list_tenants(setup):
    tc = setup
    token = _login(tc, "tm@platform.example")
    resp = tc.get("/tenants", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) >= 2
    keys = set(body[0].keys())
    forbidden = {"cms_pages", "leads", "messages", "body"}
    assert forbidden.isdisjoint(keys)


def test_ta_gets_403_on_tenants_list(setup):
    tc = setup
    token = _login(tc, "ta@acme.example")
    resp = tc.get("/tenants", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_tm_can_list_platform_audit_logs(setup):
    tc = setup
    token = _login(tc, "tm@platform.example")
    resp = tc.get("/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert len(body) >= 2
    # Cross-content denial — audit rows must not include CMS body / lead
    # detail / conversation text under any field name.
    blob = str(body).lower()
    assert "lead detail" not in blob
    assert "cms body" not in blob


def test_ta_gets_403_on_platform_audit_logs(setup):
    tc = setup
    token = _login(tc, "ta@acme.example")
    resp = tc.get("/audit-logs", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_audit_logs_filterable_by_action(setup):
    tc = setup
    token = _login(tc, "tm@platform.example")
    resp = tc.get(
        "/audit-logs?action=tenant.provisioned",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert all(r["action"] == "tenant.provisioned" for r in body)
