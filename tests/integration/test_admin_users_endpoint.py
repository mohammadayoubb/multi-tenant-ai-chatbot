# Owner: Hiba
"""Integration tests for GET /tenants/{tid}/admin-users (T033).

Covers the three required paths from tasks.md:
- Happy path: TA reads their own tenant's admin-users list.
- Cross-tenant byte-uniform 403: TA-A cannot read tenant B's path.
- Role isolation: tenant_manager cannot see per-tenant content.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.admin_auth as admin_auth_route
import app.repositories.admin_user_repo as admin_user_repo_module
from app.db.session import get_session
from app.infra.password import hash_password
from app.main import app


TENANT_A = UUID("aaaaaaaa-2222-2222-2222-222222222222")
TENANT_B = UUID("bbbbbbbb-3333-3333-3333-333333333333")


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
        self._all = list(users)

    async def get_by_email(self, email):
        return self._by_email.get(email)

    async def list_by_tenant(self, tenant_id):
        return [
            u
            for u in self._all
            if u.tenant_id == tenant_id and u.status == "active"
        ]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONCIERGE_ENV", "prod")

    users = [
        _FakeAdminUser(
            id=uuid4(),
            tenant_id=TENANT_A,
            email="alice@a.example",
            password_hash=hash_password("AlicePw1"),
            full_name="Alice A",
        ),
        _FakeAdminUser(
            id=uuid4(),
            tenant_id=TENANT_A,
            email="aaron@a.example",
            password_hash=hash_password("AaronPw1"),
            full_name="Aaron A",
        ),
        _FakeAdminUser(
            id=uuid4(),
            tenant_id=TENANT_B,
            email="bob@b.example",
            password_hash=hash_password("BobPw1"),
            full_name="Bob B",
        ),
        _FakeAdminUser(
            id=uuid4(),
            tenant_id=TENANT_A,
            email="boss@a.example",
            password_hash=hash_password("BossPw1"),
            full_name="Boss A",
            role="tenant_manager",
        ),
    ]
    repo = _UserRepo(users)
    monkeypatch.setattr(admin_auth_route, "AdminUserRepository", lambda _s: repo)
    monkeypatch.setattr(
        admin_user_repo_module, "AdminUserRepository", lambda _s: repo
    )

    async def _no_db():
        yield None

    app.dependency_overrides[get_session] = _no_db
    try:
        with TestClient(app) as tc:
            yield tc
    finally:
        app.dependency_overrides.pop(get_session, None)


def _login(tc: TestClient, email: str, password: str) -> str:
    resp = tc.post("/admin/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def test_happy_path_returns_same_tenant_admins(client: TestClient) -> None:
    token = _login(client, "alice@a.example", "AlicePw1")
    resp = client.get(
        f"/tenants/{TENANT_A}/admin-users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert isinstance(body, list)
    emails = {row["email"] for row in body}
    # Tenant A's admins (incl. the TM) are returned.
    assert emails == {"alice@a.example", "aaron@a.example", "boss@a.example"}
    # Tenant B's admin is NOT in the list.
    assert "bob@b.example" not in emails
    # Each row carries the expected shape.
    for row in body:
        assert set(row.keys()) == {"actor_id", "full_name", "email", "role", "status"}


def test_cross_tenant_path_is_byte_uniform_403(client: TestClient) -> None:
    token = _login(client, "alice@a.example", "AlicePw1")  # TENANT_A
    resp = client.get(
        f"/tenants/{TENANT_B}/admin-users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
    # Byte-uniform body: detail is the single canonical token.
    assert resp.json() == {"detail": "forbidden"}


def test_missing_auth_is_403(client: TestClient) -> None:
    resp = client.get(f"/tenants/{TENANT_A}/admin-users")
    assert resp.status_code == 403


def test_tenant_manager_for_other_tenant_is_403(client: TestClient) -> None:
    """A TM signed into tenant A still cannot read tenant B's admin-users."""
    token = _login(client, "boss@a.example", "BossPw1")
    resp = client.get(
        f"/tenants/{TENANT_B}/admin-users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
