# Owner: Nasser
"""Integration tests for PUT / PATCH / DELETE /cms/pages/{id}."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.admin_auth as admin_auth_route
import app.api.routes.cms as cms_route
from app.db.session import get_session
from app.infra.password import hash_password
from app.main import app


TENANT_A = UUID("aaaaaaaa-6666-6666-6666-666666666666")
TENANT_B = UUID("bbbbbbbb-7777-7777-7777-777777777777")


@dataclass
class _FakePage:
    id: UUID
    tenant_id: UUID
    title: str = "Page"
    slug: str = "page"
    body: str = "Body"
    source_url: str | None = None
    status: str = "draft"
    updated_at: datetime = field(default_factory=lambda: datetime.now(tz=UTC))


@dataclass
class _FakeUser:
    id: UUID
    tenant_id: UUID
    email: str
    password_hash: str
    role: str = "tenant_admin"
    full_name: str | None = None
    status: str = "active"


class _CmsRepo:
    def __init__(self) -> None:
        self.rows: dict[UUID, _FakePage] = {}

    async def get(self, page_id):
        return self.rows.get(page_id)

    async def list_pages(self, tenant_id):
        return [p for p in self.rows.values() if p.tenant_id == tenant_id]

    async def create(self, **kwargs):
        page = _FakePage(id=uuid4(), **{k: v for k, v in kwargs.items() if k != "created_by"})
        self.rows[page.id] = page
        return page

    async def update(self, page_id, tenant_id, body):
        page = await self.get(page_id)
        if page is None or page.tenant_id != tenant_id:
            return None
        for k, v in body.items():
            setattr(page, k, v)
        return page

    async def set_status(self, page_id, tenant_id, status):
        page = await self.get(page_id)
        if page is None or page.tenant_id != tenant_id:
            return None
        page.status = status
        return page

    async def soft_delete(self, page_id, tenant_id):
        page = await self.get(page_id)
        if page is None or page.tenant_id != tenant_id:
            return False
        page.status = "archived"
        return True


@dataclass
class _TenantRepoStub:
    audit_events: list[dict] = field(default_factory=list)

    async def add_audit_log(self, *, tenant_id, actor_id, actor_role, action, metadata):
        self.audit_events.append({"action": action, "metadata": metadata})


class _UserRepo:
    def __init__(self) -> None:
        self.by_email: dict[str, _FakeUser] = {}

    async def get_by_email(self, email):
        return self.by_email.get(email)


@pytest.fixture
def setup(monkeypatch):
    monkeypatch.setenv("CONCIERGE_ENV", "dev")

    cms_repo = _CmsRepo()
    tenant_repo = _TenantRepoStub()
    user_repo = _UserRepo()

    user_repo.by_email["a@acme.example"] = _FakeUser(
        id=uuid4(),
        tenant_id=TENANT_A,
        email="a@acme.example",
        password_hash=hash_password("Password1"),
    )

    page_a = _FakePage(id=uuid4(), tenant_id=TENANT_A, slug="welcome", body="hi", title="Welcome")
    page_b = _FakePage(id=uuid4(), tenant_id=TENANT_B, slug="other", body="x", title="Other")
    cms_repo.rows[page_a.id] = page_a
    cms_repo.rows[page_b.id] = page_b

    monkeypatch.setattr(admin_auth_route, "AdminUserRepository", lambda _s: user_repo)
    monkeypatch.setattr(cms_route, "CmsRepository", lambda _s: cms_repo)
    monkeypatch.setattr(cms_route, "TenantRepository", lambda _s: tenant_repo)

    async def _no_db():
        yield None

    app.dependency_overrides[get_session] = _no_db
    try:
        with TestClient(app) as tc:
            yield tc, cms_repo, tenant_repo, (page_a, page_b)
    finally:
        app.dependency_overrides.pop(get_session, None)


def _login(tc, email):
    return tc.post(
        "/admin/login", json={"email": email, "password": "Password1"}
    ).json()["token"]


def test_update_happy_path(setup):
    tc, _, tenant_repo, (page_a, _) = setup
    token = _login(tc, "a@acme.example")
    resp = tc.put(
        f"/cms/pages/{page_a.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Welcome v2", "body": "fresh body"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["title"] == "Welcome v2"
    assert any(e["action"] == "cms.page_updated" for e in tenant_repo.audit_events)


def test_update_cross_tenant_page_is_403(setup):
    tc, _, _, (_, page_b) = setup
    token = _login(tc, "a@acme.example")  # tenant A
    resp = tc.put(
        f"/cms/pages/{page_b.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "hijack"},
    )
    assert resp.status_code == 403


def test_update_body_smuggling_tenant_id_is_422(setup):
    tc, _, _, (page_a, _) = setup
    token = _login(tc, "a@acme.example")
    resp = tc.put(
        f"/cms/pages/{page_a.id}",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "X", "tenant_id": str(TENANT_B)},
    )
    assert resp.status_code == 422


def test_status_patch_emits_publish_event(setup):
    tc, cms_repo, tenant_repo, (page_a, _) = setup
    token = _login(tc, "a@acme.example")
    resp = tc.patch(
        f"/cms/pages/{page_a.id}/status",
        headers={"Authorization": f"Bearer {token}"},
        json={"status": "published"},
    )
    assert resp.status_code == 200
    assert cms_repo.rows[page_a.id].status == "published"
    assert any(e["action"] == "cms.page_published" for e in tenant_repo.audit_events)


def test_delete_soft_deletes_and_emits_audit(setup):
    tc, cms_repo, tenant_repo, (page_a, _) = setup
    token = _login(tc, "a@acme.example")
    resp = tc.delete(
        f"/cms/pages/{page_a.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 204
    assert cms_repo.rows[page_a.id].status == "archived"
    assert any(e["action"] == "cms.page_deleted" for e in tenant_repo.audit_events)
