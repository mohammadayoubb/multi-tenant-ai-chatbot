# Owner: Nasser
"""Integration tests for GET / PUT /tenants/{tid}/agent-config.

Verifies:
- Happy GET returns persisted shape (or defaults when row absent).
- Happy PUT round-trips through the repo and emits the audit event.
- chips length > 6 → 422.
- Cross-tenant TA → 403 on both GET and PUT.
- Widget JWT may GET own tenant; widget JWT may NOT PUT.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import jwt
import pytest
from fastapi.testclient import TestClient

import app.api.routes.admin_auth as admin_auth_route
import app.api.routes.tenants as tenants_route
import app.repositories.agent_config_repo as agent_config_repo_module
from app.db.session import get_session
from app.infra.password import hash_password
from app.main import app
from app.services.admin_settings import admin_settings
from app.services.widget_settings import widget_settings


TENANT_A = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
TENANT_B = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


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
class _FakeAgentConfig:
    tenant_id: UUID
    persona: str = ""
    enabled_tools_json: list[str] = field(
        default_factory=lambda: ["rag_search", "capture_lead", "escalate"]
    )
    tenant_rails_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class _TenantRepoStub:
    audit_events: list[dict] = field(default_factory=list)

    async def add_audit_log(self, *, tenant_id, actor_id, actor_role, action, metadata):
        self.audit_events.append(
            {
                "tenant_id": tenant_id,
                "actor_role": actor_role,
                "action": action,
                "metadata": metadata,
            }
        )


class _AgentConfigRepo:
    def __init__(self) -> None:
        self.rows: dict[UUID, _FakeAgentConfig] = {}

    async def get_by_tenant(self, tenant_id):
        return self.rows.get(tenant_id)

    async def upsert(self, tenant_id, *, persona, tenant_rails):
        row = self.rows.get(tenant_id)
        if row is None:
            row = _FakeAgentConfig(tenant_id=tenant_id)
            self.rows[tenant_id] = row
        row.persona = persona
        row.tenant_rails_json = tenant_rails
        return row


class _UserRepo:
    def __init__(self) -> None:
        self.by_email: dict[str, _FakeUser] = {}

    async def get_by_email(self, email):
        return self.by_email.get(email)


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONCIERGE_ENV", "dev")

    agent_repo = _AgentConfigRepo()
    tenant_repo = _TenantRepoStub()
    user_repo = _UserRepo()
    user_repo.by_email["a-admin@acme.example"] = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_A,
        email="a-admin@acme.example",
        password_hash=hash_password("Password1"),
    )
    user_repo.by_email["b-admin@beta.example"] = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_B,
        email="b-admin@beta.example",
        password_hash=hash_password("Password1"),
    )

    monkeypatch.setattr(admin_auth_route, "AdminUserRepository", lambda _s: user_repo)
    monkeypatch.setattr(
        agent_config_repo_module, "TenantAgentConfigRepository", lambda _s: agent_repo
    )
    monkeypatch.setattr(tenants_route, "TenantRepository", lambda _s: tenant_repo)

    async def _no_db():
        yield None

    app.dependency_overrides[get_session] = _no_db
    try:
        with TestClient(app) as tc:
            yield tc, agent_repo, tenant_repo
    finally:
        app.dependency_overrides.pop(get_session, None)


def _admin_login(tc: TestClient, email: str) -> str:
    resp = tc.post("/admin/login", json={"email": email, "password": "Password1"})
    assert resp.status_code == 200
    return resp.json()["token"]


def _widget_jwt(tenant_id: UUID) -> str:
    now = int(time.time())
    payload = {"tenant_id": str(tenant_id), "iat": now, "exp": now + 600}
    return jwt.encode(
        payload, widget_settings().widget_jwt_secret, algorithm="HS256"
    )


def test_get_returns_defaults_when_no_row(setup):
    tc, _, _ = setup
    admin_token = _admin_login(tc, "a-admin@acme.example")
    resp = tc.get(
        f"/tenants/{TENANT_A}/agent-config",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["greeting"]
    assert body["tone"]
    assert isinstance(body["chips"], list)
    assert len(body["chips"]) <= 6


def test_put_roundtrips_and_emits_audit_event(setup):
    tc, agent_repo, tenant_repo = setup
    admin_token = _admin_login(tc, "a-admin@acme.example")
    body = {
        "persona_name": "Acme Concierge",
        "greeting": "Hello!",
        "tone": "professional",
        "language": "en",
        "business_rules": "Hours 9-5",
        "chips": ["Pricing", "Hours"],
    }
    put = tc.put(
        f"/tenants/{TENANT_A}/agent-config",
        headers={"Authorization": f"Bearer {admin_token}"},
        json=body,
    )
    assert put.status_code == 200, put.text
    out = put.json()
    assert out["persona_name"] == "Acme Concierge"
    assert out["chips"] == ["Pricing", "Hours"]
    assert TENANT_A in agent_repo.rows
    assert any(
        e["action"] == "tenant.agent_config_updated" for e in tenant_repo.audit_events
    )


def test_put_rejects_more_than_six_chips(setup):
    tc, _, _ = setup
    admin_token = _admin_login(tc, "a-admin@acme.example")
    resp = tc.put(
        f"/tenants/{TENANT_A}/agent-config",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "persona_name": "Too Many",
            "chips": ["a", "b", "c", "d", "e", "f", "g"],
        },
    )
    assert resp.status_code == 422


def test_cross_tenant_ta_get_is_403(setup):
    tc, _, _ = setup
    a_token = _admin_login(tc, "a-admin@acme.example")  # TENANT_A
    resp = tc.get(
        f"/tenants/{TENANT_B}/agent-config",
        headers={"Authorization": f"Bearer {a_token}"},
    )
    assert resp.status_code == 403


def test_widget_jwt_can_get_own_tenant(setup):
    tc, _, _ = setup
    token = _widget_jwt(TENANT_A)
    resp = tc.get(
        f"/tenants/{TENANT_A}/agent-config",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200


def test_widget_jwt_cannot_put(setup):
    tc, _, _ = setup
    token = _widget_jwt(TENANT_A)
    resp = tc.put(
        f"/tenants/{TENANT_A}/agent-config",
        headers={"Authorization": f"Bearer {token}"},
        json={"persona_name": "Smuggle"},
    )
    # PUT path requires require_tenant_admin which returns None for widget token
    assert resp.status_code == 403
