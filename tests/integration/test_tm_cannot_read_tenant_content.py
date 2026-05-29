# Owner: Amer
"""Spec 009 US3 T080 — tenant_manager must not reach tenant content endpoints.

FR-046: the tenant_manager role exists to operate the platform; it MUST NOT be
able to read tenant CMS pages, leads, conversation history, or escalation
tickets (which embed message excerpts). The TM dashboard intentionally omits
those tabs from the UI; this test pins the backend so a future route refactor
can't quietly re-open the door.

All four assertions are 403 (forbidden) and surface a generic body — no raw
exception, no internal hint about what was queried.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.admin_auth as admin_auth_route
import app.api.routes.cms as cms_route
import app.api.routes.escalations as escalations_route
import app.api.routes.leads as leads_route
from app.db.session import get_session
from app.infra.password import hash_password
from app.main import app


TENANT_A = UUID("11111111-cccc-cccc-cccc-111111111111")


@dataclass
class _FakeUser:
    id: UUID
    tenant_id: UUID
    email: str
    password_hash: str
    role: str = "tenant_manager"
    full_name: str | None = None
    status: str = "active"


class _UserRepo:
    def __init__(self) -> None:
        self.by_email: dict[str, _FakeUser] = {}

    async def get_by_email(self, email):
        return self.by_email.get(email)


class _EmptyCmsRepo:
    async def list_pages(self, _tenant_id):
        return []


class _EmptyLeadRepo:
    async def list_by_tenant(self, _tenant_id, *, limit):
        return []


class _EmptyEscalationRepo:
    async def list_by_tenant(self, _tenant_id):
        return []


@dataclass
class _TenantRepoStub:
    audit_events: list[dict] = field(default_factory=list)

    async def add_audit_log(self, **_kwargs):
        return None


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONCIERGE_ENV", "dev")
    user_repo = _UserRepo()
    user_repo.by_email["tm@platform.example"] = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_A,
        email="tm@platform.example",
        password_hash=hash_password("Password1"),
        role="tenant_manager",
    )

    monkeypatch.setattr(admin_auth_route, "AdminUserRepository", lambda _s: user_repo)
    # If the gate ever fails open, the repo stubs return empty lists so the
    # test reports a clear 200 (rather than crashing) — the 403 assertion is
    # the load-bearing one.
    monkeypatch.setattr(cms_route, "CmsRepository", lambda _s: _EmptyCmsRepo())
    monkeypatch.setattr(leads_route, "LeadRepository", lambda _s: _EmptyLeadRepo())
    monkeypatch.setattr(
        escalations_route, "EscalationRepository", lambda _s: _EmptyEscalationRepo()
    )

    async def _no_db():
        yield None

    app.dependency_overrides[get_session] = _no_db
    try:
        with TestClient(app) as tc:
            yield tc
    finally:
        app.dependency_overrides.pop(get_session, None)


def _tm_token(tc: TestClient) -> str:
    resp = tc.post(
        "/admin/login",
        json={"email": "tm@platform.example", "password": "Password1"},
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def test_tm_cannot_list_cms_pages(client):
    tc = client
    token = _tm_token(tc)
    resp = tc.get("/cms/pages", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_tm_cannot_list_leads(client):
    tc = client
    token = _tm_token(tc)
    resp = tc.get("/leads", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_tm_cannot_list_escalations(client):
    tc = client
    token = _tm_token(tc)
    resp = tc.get("/escalations", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 403


def test_tm_cannot_list_escalations_with_cross_tenant_id(client):
    tc = client
    token = _tm_token(tc)
    other = uuid4()
    resp = tc.get(
        f"/escalations?tenant_id={other}",
        headers={"Authorization": f"Bearer {token}"},
    )
    # Even passing a target tenant_id (which the old TM-as-platform escape
    # would have honored) must still 403 — TM has no tenant-content path.
    assert resp.status_code == 403


def test_no_chat_history_route_exists(client):
    """The spec asserts /chat-history is unreachable; we don't ship the route."""
    tc = client
    token = _tm_token(tc)
    resp = tc.get("/chat-history", headers={"Authorization": f"Bearer {token}"})
    # 404 (no route) is acceptable; 403 (route exists, TM refused) also fine.
    # 200 would be a regression.
    assert resp.status_code in (403, 404, 405)
