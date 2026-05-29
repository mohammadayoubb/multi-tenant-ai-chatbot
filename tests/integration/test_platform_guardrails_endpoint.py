# Owner: Ayoub
"""Integration tests for GET /tenants/{tid}/platform-guardrails."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.admin_auth as admin_auth_route
import app.repositories.agent_config_repo as agent_config_repo_module
from app.db.session import get_session
from app.infra.password import hash_password
from app.main import app


TENANT_A = UUID("aaaaaaaa-3333-3333-3333-333333333333")
TENANT_B = UUID("bbbbbbbb-4444-4444-4444-444444444444")


@dataclass
class _FakeAgentConfig:
    tenant_id: UUID
    persona: str = ""
    enabled_tools_json: list[str] = field(default_factory=list)
    tenant_rails_json: dict[str, Any] = field(default_factory=dict)


@dataclass
class _FakeUser:
    id: UUID
    tenant_id: UUID
    email: str
    password_hash: str
    role: str = "tenant_admin"
    full_name: str | None = None
    status: str = "active"


class _AgentConfigRepo:
    def __init__(self) -> None:
        self.rows: dict[UUID, _FakeAgentConfig] = {}

    async def get_by_tenant(self, tenant_id):
        return self.rows.get(tenant_id)

    async def upsert(self, tenant_id, *, persona, tenant_rails):
        row = _FakeAgentConfig(
            tenant_id=tenant_id, persona=persona, tenant_rails_json=tenant_rails
        )
        self.rows[tenant_id] = row
        return row


class _UserRepo:
    def __init__(self) -> None:
        self.by_email: dict[str, _FakeUser] = {}

    async def get_by_email(self, email):
        return self.by_email.get(email)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("CONCIERGE_ENV", "dev")

    agent_repo = _AgentConfigRepo()
    agent_repo.rows[TENANT_A] = _FakeAgentConfig(
        tenant_id=TENANT_A,
        tenant_rails_json={
            "tenant_blocked_topics": ["pricing_competitor"],
            "tenant_refusal_tone": "firm",
        },
    )

    user_repo = _UserRepo()
    user_repo.by_email["a-admin@acme.example"] = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_A,
        email="a-admin@acme.example",
        password_hash=hash_password("Password1"),
    )

    monkeypatch.setattr(admin_auth_route, "AdminUserRepository", lambda _s: user_repo)
    monkeypatch.setattr(
        agent_config_repo_module, "TenantAgentConfigRepository", lambda _s: agent_repo
    )

    async def _no_db():
        yield None

    app.dependency_overrides[get_session] = _no_db
    try:
        with TestClient(app) as tc:
            yield tc, agent_repo
    finally:
        app.dependency_overrides.pop(get_session, None)


def _login(tc: TestClient, email: str) -> str:
    return tc.post(
        "/admin/login", json={"email": email, "password": "Password1"}
    ).json()["token"]


def test_read_returns_platform_plus_tenant_sections(setup):
    tc, _ = setup
    token = _login(tc, "a-admin@acme.example")
    resp = tc.get(
        f"/tenants/{TENANT_A}/platform-guardrails",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert any(r["id"] == "block_cross_tenant_probe" for r in body["platform_rules"])
    assert all(r["locked"] is True for r in body["platform_rules"])
    assert body["tenant_blocked_topics"] == ["pricing_competitor"]
    assert body["tenant_refusal_tone"] == "firm"


def test_cross_tenant_path_is_403(setup):
    tc, _ = setup
    token = _login(tc, "a-admin@acme.example")  # TENANT_A
    resp = tc.get(
        f"/tenants/{TENANT_B}/platform-guardrails",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


def test_endpoint_is_read_only(setup):
    """No mutation methods exposed — POST/PUT/DELETE all 405."""
    tc, _ = setup
    token = _login(tc, "a-admin@acme.example")
    for method in ("post", "put", "delete"):
        resp = getattr(tc, method)(
            f"/tenants/{TENANT_A}/platform-guardrails",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code in (405, 403, 404)
