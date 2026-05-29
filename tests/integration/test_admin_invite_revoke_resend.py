# Owner: Amer
"""Integration coverage for POST /admin/invites/{token}/revoke + .../resend.

Uses the same in-memory fake-repo pattern as test_admin_invite_flow.py.
Asserts:
- happy revoke marks revoked_at and emits an audit-log entry
- already-used invite → 409
- already-revoked invite → 409
- cross-tenant TA → 403; TM → 200 (manager scope crosses tenants by design)
- happy resend rotates token + extends expires_at
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


TENANT_A = UUID("11111111-1111-1111-1111-111111111111")
TENANT_B = UUID("22222222-2222-2222-2222-222222222222")


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
    revoked_at: datetime | None = None


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

    async def mark_revoked(self, token, *, revoked_at):
        row = self.rows.get(token)
        if row is None:
            return None
        row.revoked_at = revoked_at
        return row

    async def resend(self, token, *, new_token, new_expires_at):
        row = self.rows.pop(token, None)
        if row is None:
            return None
        row.token = new_token
        row.expires_at = new_expires_at
        self.rows[new_token] = row
        return row


@dataclass
class _TenantRepo:
    tenants: list[_FakeTenant] = field(default_factory=list)
    audit_events: list[dict] = field(default_factory=list)

    async def get_by_id(self, tenant_id):
        for t in self.tenants:
            if t.id == tenant_id:
                return t
        return None

    async def add_audit_log(self, *, tenant_id, actor_id, actor_role, action, metadata):
        self.audit_events.append(
            {
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "actor_role": actor_role,
                "action": action,
                "metadata": metadata,
            }
        )


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONCIERGE_ENV", "dev")

    user_repo = _UserRepo()
    user_repo.by_email["a-admin@acme.example"] = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_A,
        email="a-admin@acme.example",
        password_hash=hash_password("Password1"),
        role="tenant_admin",
    )
    user_repo.by_email["b-admin@beta.example"] = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_B,
        email="b-admin@beta.example",
        password_hash=hash_password("Password1"),
        role="tenant_admin",
    )
    user_repo.by_email["tm@platform.example"] = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_A,
        email="tm@platform.example",
        password_hash=hash_password("Password1"),
        role="tenant_manager",
    )

    invite_repo = _InviteRepo()
    tenant_repo = _TenantRepo(
        [
            _FakeTenant(id=TENANT_A, name="Acme"),
            _FakeTenant(id=TENANT_B, name="Beta"),
        ]
    )

    monkeypatch.setattr(admin_auth_route, "AdminUserRepository", lambda _s: user_repo)
    monkeypatch.setattr(admin_invites_route, "AdminInviteRepository", lambda _s: invite_repo)
    monkeypatch.setattr(admin_invites_route, "AdminUserRepository", lambda _s: user_repo)
    monkeypatch.setattr(admin_invites_route, "TenantRepository", lambda _s: tenant_repo)
    monkeypatch.setattr(admin_invites_route, "_TenantRepoForAudit", lambda _s: tenant_repo)

    async def _no_db():
        yield None

    app.dependency_overrides[get_session] = _no_db
    try:
        with TestClient(app) as tc:
            yield tc, user_repo, invite_repo, tenant_repo
    finally:
        app.dependency_overrides.pop(get_session, None)


def _login(tc: TestClient, email: str) -> str:
    resp = tc.post("/admin/login", json={"email": email, "password": "Password1"})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def _seed_invite(
    invite_repo: _InviteRepo,
    *,
    tenant_id: UUID,
    used: bool = False,
    revoked: bool = False,
) -> UUID:
    token = uuid4()
    invite_repo.rows[token] = _FakeInvite(
        id=uuid4(),
        token=token,
        tenant_id=tenant_id,
        email="invitee@example.com",
        role="tenant_admin",
        invited_by="a-admin@acme.example",
        expires_at=datetime.now(tz=UTC) + timedelta(days=1),
        used_at=datetime.now(tz=UTC) if used else None,
        revoked_at=datetime.now(tz=UTC) if revoked else None,
    )
    return token


def test_revoke_happy_path_marks_revoked_and_audits(client):
    tc, _, invite_repo, tenant_repo = client
    token = _seed_invite(invite_repo, tenant_id=TENANT_A)
    admin_token = _login(tc, "a-admin@acme.example")

    resp = tc.post(
        f"/admin/invites/{token}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["ok"] is True
    assert body["revoked_at"] is not None
    assert invite_repo.rows[token].revoked_at is not None
    assert any(e["action"] == "admin.invite_revoked" for e in tenant_repo.audit_events)


def test_revoke_already_used_is_409(client):
    tc, _, invite_repo, _ = client
    token = _seed_invite(invite_repo, tenant_id=TENANT_A, used=True)
    admin_token = _login(tc, "a-admin@acme.example")

    resp = tc.post(
        f"/admin/invites/{token}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409
    assert resp.content == b'{"error":"invite_conflict"}'


def test_revoke_already_revoked_is_409(client):
    tc, _, invite_repo, _ = client
    token = _seed_invite(invite_repo, tenant_id=TENANT_A, revoked=True)
    admin_token = _login(tc, "a-admin@acme.example")

    resp = tc.post(
        f"/admin/invites/{token}/revoke",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409


def test_revoke_cross_tenant_ta_is_403(client):
    tc, _, invite_repo, _ = client
    token = _seed_invite(invite_repo, tenant_id=TENANT_B)
    a_token = _login(tc, "a-admin@acme.example")  # TA on tenant A

    resp = tc.post(
        f"/admin/invites/{token}/revoke",
        headers={"Authorization": f"Bearer {a_token}"},
    )
    assert resp.status_code == 403


def test_revoke_cross_tenant_tm_is_200(client):
    tc, _, invite_repo, _ = client
    token = _seed_invite(invite_repo, tenant_id=TENANT_B)
    tm_token = _login(tc, "tm@platform.example")  # TM scope: any tenant

    resp = tc.post(
        f"/admin/invites/{token}/revoke",
        headers={"Authorization": f"Bearer {tm_token}"},
    )
    assert resp.status_code == 200


def test_resend_rotates_token_and_extends_expiry(client):
    tc, _, invite_repo, tenant_repo = client
    token = _seed_invite(invite_repo, tenant_id=TENANT_A)
    original_expires = invite_repo.rows[token].expires_at
    admin_token = _login(tc, "a-admin@acme.example")

    resp = tc.post(
        f"/admin/invites/{token}/resend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["token"] != str(token)
    new_token = UUID(body["token"])
    assert new_token in invite_repo.rows
    assert invite_repo.rows[new_token].expires_at > original_expires
    assert any(e["action"] == "admin.invite_resent" for e in tenant_repo.audit_events)


def test_resend_used_invite_is_409(client):
    tc, _, invite_repo, _ = client
    token = _seed_invite(invite_repo, tenant_id=TENANT_A, used=True)
    admin_token = _login(tc, "a-admin@acme.example")

    resp = tc.post(
        f"/admin/invites/{token}/resend",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert resp.status_code == 409
