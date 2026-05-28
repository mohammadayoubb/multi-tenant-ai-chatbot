# Owner: Amer
"""End-to-end admin invite HTTP flow with the real FastAPI router stack.

Login as an inviter -> POST /admin/invites -> GET /admin/invites/{token}
-> POST /admin/invites/{token}/accept -> login as the new admin.

CONCIERGE_ENV=dev keeps the dev-headers fallback open so existing fixtures
work; the auth path being exercised here is the real JWT path.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.admin_auth as admin_auth_route
import app.api.routes.admin_invites as admin_invites_route
from app.db.session import get_session
from app.infra.password import hash_password
from app.main import app


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
class _FakeInvite:
    id: UUID
    token: UUID
    tenant_id: UUID
    email: str
    role: str
    invited_by: str
    expires_at: datetime
    used_at: datetime | None = None


@dataclass
class _FakeTenant:
    id: UUID
    name: str


class _UserRepo:
    def __init__(self) -> None:
        self.by_email: dict[str, _FakeUser] = {}

    async def get_by_email(self, email):
        return self.by_email.get(email)

    async def create(self, *, tenant_id, email, password_hash, role="tenant_admin"):
        user = _FakeUser(
            id=uuid4(),
            tenant_id=tenant_id,
            email=email,
            password_hash=password_hash,
            role=role,
        )
        self.by_email[email] = user
        return user


class _InviteRepo:
    def __init__(self) -> None:
        self.rows: dict[UUID, _FakeInvite] = {}

    async def create(self, **kwargs):
        invite = _FakeInvite(id=uuid4(), **kwargs)
        self.rows[invite.token] = invite
        return invite

    async def get_by_token(self, token):
        return self.rows.get(token)

    async def mark_used(self, invite, *, used_at):
        invite.used_at = used_at


@dataclass
class _TenantRepo:
    tenants: list[_FakeTenant] = field(default_factory=list)

    async def get_by_id(self, tenant_id):
        for t in self.tenants:
            if t.id == tenant_id:
                return t
        return None


TENANT_ID = UUID("44444444-4444-4444-4444-444444444444")


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONCIERGE_ENV", "dev")

    user_repo = _UserRepo()
    user_repo.by_email["boss@acme.example"] = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_ID,
        email="boss@acme.example",
        password_hash=hash_password("BossPw123"),
        role="tenant_manager",
    )
    invite_repo = _InviteRepo()
    tenant_repo = _TenantRepo([_FakeTenant(id=TENANT_ID, name="Acme Inc.")])

    # Both routes wrap their fakes — every constructor call returns the same
    # in-memory state so create -> get -> accept share rows.
    monkeypatch.setattr(admin_auth_route, "AdminUserRepository", lambda _s: user_repo)
    monkeypatch.setattr(admin_invites_route, "AdminInviteRepository", lambda _s: invite_repo)
    monkeypatch.setattr(admin_invites_route, "AdminUserRepository", lambda _s: user_repo)
    monkeypatch.setattr(admin_invites_route, "TenantRepository", lambda _s: tenant_repo)

    async def _no_db():
        yield None

    app.dependency_overrides[get_session] = _no_db
    try:
        with TestClient(app) as tc:
            yield tc, user_repo, invite_repo
    finally:
        app.dependency_overrides.pop(get_session, None)


def _login(tc: TestClient, email: str, password: str) -> str:
    resp = tc.post("/admin/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def test_full_invite_flow_creates_admin_and_signs_them_in(client) -> None:
    tc, user_repo, invite_repo = client

    boss_token = _login(tc, "boss@acme.example", "BossPw123")
    create = tc.post(
        "/admin/invites",
        headers={"Authorization": f"Bearer {boss_token}"},
        json={"email": "newbie@acme.example", "role": "tenant_admin"},
    )
    assert create.status_code == 200, create.text
    invite_body = create.json()
    assert invite_body["tenant_id"] == str(TENANT_ID)
    token = invite_body["token"]

    details = tc.get(f"/admin/invites/{token}")
    assert details.status_code == 200, details.text
    assert details.json() == {
        "email": "newbie@acme.example",
        "role": "tenant_admin",
        "tenant_name": "Acme Inc.",
        "expires_at": invite_body["expires_at"],
        "status": "pending",
    }

    accept = tc.post(
        f"/admin/invites/{token}/accept",
        json={
            "full_name": "New Bie",
            "password": "hunter2letter",
            "confirm_password": "hunter2letter",
        },
    )
    assert accept.status_code == 200, accept.text
    body = accept.json()
    assert body["tenant_id"] == str(TENANT_ID)
    assert body["role"] == "tenant_admin"

    # The new admin can log in immediately.
    new_token = _login(tc, "newbie@acme.example", "hunter2letter")
    assert new_token

    # Invite is marked used.
    invite_row = invite_repo.rows[UUID(token)]
    assert invite_row.used_at is not None


def test_invite_create_rejects_unauthenticated(client) -> None:
    tc, _, _ = client
    resp = tc.post("/admin/invites", json={"email": "newbie@acme.example"})
    assert resp.status_code == 403


def test_invite_create_body_cannot_override_tenant_id(client) -> None:
    """The schema has no `tenant_id` field; even sent as an extra it's ignored."""
    tc, _, invite_repo = client
    boss_token = _login(tc, "boss@acme.example", "BossPw123")
    foreign_tenant = uuid4()
    resp = tc.post(
        "/admin/invites",
        headers={"Authorization": f"Bearer {boss_token}"},
        json={
            "email": "newbie@acme.example",
            "tenant_id": str(foreign_tenant),
            "role": "tenant_admin",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["tenant_id"] == str(TENANT_ID)  # inviter's tenant, NOT body
    stored = invite_repo.rows[UUID(body["token"])]
    assert stored.tenant_id == TENANT_ID
    assert stored.tenant_id != foreign_tenant


def test_invite_details_unknown_token_is_404(client) -> None:
    tc, _, _ = client
    resp = tc.get(f"/admin/invites/{uuid4()}")
    assert resp.status_code == 404
    assert resp.content == b'{"error":"invite_unavailable"}'


def test_invite_accept_rejects_password_mismatch(client) -> None:
    tc, _, invite_repo = client
    boss_token = _login(tc, "boss@acme.example", "BossPw123")
    invite_body = tc.post(
        "/admin/invites",
        headers={"Authorization": f"Bearer {boss_token}"},
        json={"email": "newbie@acme.example", "role": "tenant_admin"},
    ).json()
    resp = tc.post(
        f"/admin/invites/{invite_body['token']}/accept",
        json={
            "full_name": "New Bie",
            "password": "hunter2letter",
            "confirm_password": "different1",
        },
    )
    assert resp.status_code == 400
    assert resp.content == b'{"error":"invite_unavailable"}'


def test_invite_accept_rejects_weak_password(client) -> None:
    tc, _, invite_repo = client
    boss_token = _login(tc, "boss@acme.example", "BossPw123")
    invite_body = tc.post(
        "/admin/invites",
        headers={"Authorization": f"Bearer {boss_token}"},
        json={"email": "newbie@acme.example", "role": "tenant_admin"},
    ).json()
    resp = tc.post(
        f"/admin/invites/{invite_body['token']}/accept",
        json={
            "full_name": "New Bie",
            "password": "alllettersnodigit",
            "confirm_password": "alllettersnodigit",
        },
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"] == "weak_password"
    assert "digit" in body["message"]


def test_invite_accept_is_single_use(client) -> None:
    tc, _, _ = client
    boss_token = _login(tc, "boss@acme.example", "BossPw123")
    invite_body = tc.post(
        "/admin/invites",
        headers={"Authorization": f"Bearer {boss_token}"},
        json={"email": "newbie@acme.example", "role": "tenant_admin"},
    ).json()
    first = tc.post(
        f"/admin/invites/{invite_body['token']}/accept",
        json={
            "full_name": "New Bie",
            "password": "hunter2letter",
            "confirm_password": "hunter2letter",
        },
    )
    assert first.status_code == 200

    second = tc.post(
        f"/admin/invites/{invite_body['token']}/accept",
        json={
            "full_name": "Someone Else",
            "password": "totallydifferent1",
            "confirm_password": "totallydifferent1",
        },
    )
    assert second.status_code == 400


def test_login_suspended_user_returns_canonical_401(client) -> None:
    tc, user_repo, _ = client
    user_repo.by_email["suspended@acme.example"] = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_ID,
        email="suspended@acme.example",
        password_hash=hash_password("CorrectPw1"),
        role="tenant_admin",
        status="suspended",
    )
    resp = tc.post(
        "/admin/login",
        json={"email": "suspended@acme.example", "password": "CorrectPw1"},
    )
    assert resp.status_code == 401
    assert resp.content == b'{"error":"invalid_credentials"}'
