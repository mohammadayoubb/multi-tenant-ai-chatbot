# Owner: Hiba
"""Integration tests for PUT /tenants/{tid}/settings."""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.admin_auth as admin_auth_route
import app.repositories.tenant_settings_repo as tenant_settings_repo_module
import app.api.routes.tenants as tenants_route
from app.db.session import get_session
from app.infra.password import hash_password
from app.main import app


TENANT_A = UUID("aaaaaaaa-5555-5555-5555-555555555555")


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
class _FakeSettings:
    tenant_id: UUID
    default_invite_ttl_seconds: int = 604800
    rate_limit_chat_per_minute: int = 30
    rate_limit_token_per_minute: int = 60


class _SettingsRepo:
    def __init__(self) -> None:
        self.rows: dict[UUID, _FakeSettings] = {}

    async def get_or_create(self, tenant_id):
        if tenant_id not in self.rows:
            self.rows[tenant_id] = _FakeSettings(tenant_id=tenant_id)
        return self.rows[tenant_id]

    async def update(self, tenant_id, body):
        row = await self.get_or_create(tenant_id)
        for k, v in body.items():
            setattr(row, k, v)
        return row


@dataclass
class _TenantRepoStub:
    audit_events: list[dict] = field(default_factory=list)

    async def add_audit_log(self, *, tenant_id, actor_id, actor_role, action, metadata):
        self.audit_events.append({"action": action, "actor_role": actor_role})


class _UserRepo:
    def __init__(self) -> None:
        self.by_email: dict[str, _FakeUser] = {}

    async def get_by_email(self, email):
        return self.by_email.get(email)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("CONCIERGE_ENV", "dev")

    settings_repo = _SettingsRepo()
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
    monkeypatch.setattr(
        tenant_settings_repo_module,
        "TenantSettingsRepository",
        lambda _s: settings_repo,
    )
    monkeypatch.setattr(tenants_route, "TenantRepository", lambda _s: tenant_repo)

    async def _no_db():
        yield None

    app.dependency_overrides[get_session] = _no_db
    try:
        with TestClient(app) as tc:
            yield tc, settings_repo, tenant_repo
    finally:
        app.dependency_overrides.pop(get_session, None)


def _login(tc, email):
    return tc.post(
        "/admin/login", json={"email": email, "password": "Password1"}
    ).json()["token"]


def _valid_body():
    return {
        "default_invite_ttl_seconds": 86400,
        "rate_limit_chat_per_minute": 50,
        "rate_limit_token_per_minute": 100,
    }


def test_tenant_manager_can_put(setup):
    tc, _, tenant_repo = setup
    token = _login(tc, "tm@platform.example")
    resp = tc.put(
        f"/tenants/{TENANT_A}/settings",
        headers={"Authorization": f"Bearer {token}"},
        json=_valid_body(),
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["rate_limit_chat_per_minute"] == 50
    assert any(e["action"] == "tenant_settings_updated" for e in tenant_repo.audit_events)


def test_tenant_admin_is_403(setup):
    tc, _, _ = setup
    token = _login(tc, "ta@acme.example")
    resp = tc.put(
        f"/tenants/{TENANT_A}/settings",
        headers={"Authorization": f"Bearer {token}"},
        json=_valid_body(),
    )
    assert resp.status_code == 403


def test_out_of_bounds_is_422(setup):
    tc, _, _ = setup
    token = _login(tc, "tm@platform.example")
    body = _valid_body()
    body["default_invite_ttl_seconds"] = 60  # below 3600 floor
    resp = tc.put(
        f"/tenants/{TENANT_A}/settings",
        headers={"Authorization": f"Bearer {token}"},
        json=body,
    )
    assert resp.status_code == 422
