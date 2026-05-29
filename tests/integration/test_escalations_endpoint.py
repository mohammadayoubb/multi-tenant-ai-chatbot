# Owner: Nasser
"""Integration tests for GET /escalations + PATCH /escalations/{id}."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.admin_auth as admin_auth_route
import app.api.routes.escalations as escalations_route
from app.db.session import get_session
from app.infra.password import hash_password
from app.main import app


TENANT_A = UUID("aaaaaaaa-1111-1111-1111-111111111111")
TENANT_B = UUID("bbbbbbbb-2222-2222-2222-222222222222")


@dataclass
class _FakeTicket:
    id: UUID
    tenant_id: UUID
    conversation_id: UUID = field(default_factory=uuid4)
    reason: str = "Customer wants a callback."
    status: str = "open"
    assigned_to: str | None = None
    created_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass
class _FakeUser:
    id: UUID
    tenant_id: UUID
    email: str
    password_hash: str
    role: str = "tenant_admin"
    full_name: str | None = "Jane Doe"
    status: str = "active"


class _EscalationRepo:
    def __init__(self) -> None:
        self.rows: dict[UUID, _FakeTicket] = {}

    async def list_by_tenant(self, tenant_id):
        return [t for t in self.rows.values() if t.tenant_id == tenant_id]

    async def get(self, ticket_id):
        return self.rows.get(ticket_id)

    async def update_status_and_assignee(
        self, ticket_id, *, status, assignee_id, update_assignee
    ):
        row = self.rows.get(ticket_id)
        if row is None:
            return None
        if status is not None:
            row.status = status
        if update_assignee:
            row.assigned_to = assignee_id
        return row


class _AdminUserRepo:
    def __init__(self) -> None:
        self.users: dict[str, _FakeUser] = {}
        self.by_id: dict[UUID, _FakeUser] = {}

    async def get_by_email(self, email):
        return self.users.get(email)

    async def get_by_id(self, user_id):
        return self.by_id.get(user_id)

    async def list_by_tenant(self, tenant_id):
        return [u for u in self.by_id.values() if u.tenant_id == tenant_id]


@dataclass
class _TenantRepoStub:
    audit_events: list[dict] = field(default_factory=list)

    async def add_audit_log(self, *, tenant_id, actor_id, actor_role, action, metadata):
        self.audit_events.append({"action": action, "metadata": metadata})


@pytest.fixture
def setup(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONCIERGE_ENV", "dev")

    repo = _EscalationRepo()
    user_repo = _AdminUserRepo()
    tenant_repo = _TenantRepoStub()

    a_admin = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_A,
        email="a-admin@acme.example",
        password_hash=hash_password("Password1"),
    )
    a_assignee = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_A,
        email="assignee@acme.example",
        password_hash=hash_password("Password1"),
        full_name="Aria Smith",
    )
    b_admin = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_B,
        email="b-admin@beta.example",
        password_hash=hash_password("Password1"),
    )
    for u in (a_admin, a_assignee, b_admin):
        user_repo.users[u.email] = u
        user_repo.by_id[u.id] = u

    ticket_a = _FakeTicket(id=uuid4(), tenant_id=TENANT_A)
    ticket_b = _FakeTicket(id=uuid4(), tenant_id=TENANT_B)
    repo.rows[ticket_a.id] = ticket_a
    repo.rows[ticket_b.id] = ticket_b

    monkeypatch.setattr(admin_auth_route, "AdminUserRepository", lambda _s: user_repo)
    monkeypatch.setattr(escalations_route, "EscalationRepository", lambda _s: repo)
    monkeypatch.setattr(escalations_route, "AdminUserRepository", lambda _s: user_repo)
    monkeypatch.setattr(escalations_route, "TenantRepository", lambda _s: tenant_repo)

    async def _no_db():
        yield None

    app.dependency_overrides[get_session] = _no_db
    try:
        with TestClient(app) as tc:
            yield tc, repo, user_repo, tenant_repo, (
                ticket_a,
                ticket_b,
                a_admin,
                a_assignee,
                b_admin,
            )
    finally:
        app.dependency_overrides.pop(get_session, None)


def _login(tc: TestClient, email: str) -> str:
    return tc.post(
        "/admin/login", json={"email": email, "password": "Password1"}
    ).json()["token"]


def test_list_filters_by_jwt_tenant(setup):
    tc, _, _, _, fixture = setup
    ticket_a, ticket_b, *_ = fixture
    token = _login(tc, "a-admin@acme.example")
    resp = tc.get("/escalations", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    ids = {row["ticket_id"] for row in resp.json()}
    assert str(ticket_a.id) in ids
    assert str(ticket_b.id) not in ids


def test_patch_status_emits_audit(setup):
    tc, _, _, tenant_repo, fixture = setup
    ticket_a, *_ = fixture
    token = _login(tc, "a-admin@acme.example")
    resp = tc.patch(
        f"/escalations/{ticket_a.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "in_progress"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"
    assert any(e["action"] == "escalation.status_changed" for e in tenant_repo.audit_events)


def test_patch_foreign_tenant_assignee_is_422(setup):
    tc, _, _, _, fixture = setup
    ticket_a, _, _, _, b_admin = fixture
    token = _login(tc, "a-admin@acme.example")
    resp = tc.patch(
        f"/escalations/{ticket_a.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"assignee_id": str(b_admin.id)},
    )
    assert resp.status_code == 422


def test_patch_cross_tenant_ticket_is_403(setup):
    tc, _, _, _, fixture = setup
    _, ticket_b, *_ = fixture
    token = _login(tc, "a-admin@acme.example")  # TENANT_A
    resp = tc.patch(
        f"/escalations/{ticket_b.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "resolved"},
    )
    assert resp.status_code == 403
