# Owner: Amer
"""Integration test for POST /cms/pages tenant-id discipline (Spec 009 US2, T061).

Asserts the two invariants the admin Create form depends on:
  1. tenant_id ALWAYS derives from the admin JWT (never from the request body).
  2. A body that smuggles a tenant_id field is rejected 422 by `extra=forbid`.

The CMS Create form lands in T070; this test fixes the contract so the form's
client-side payload remains tenant_id-free.
"""

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


TENANT_A = UUID("aaaaaaaa-cccc-1111-1111-111111111111")
TENANT_B = UUID("bbbbbbbb-cccc-2222-2222-222222222222")


@dataclass
class _FakeAdminUser:
    id: UUID
    tenant_id: UUID
    email: str
    password_hash: str
    role: str = "tenant_admin"
    full_name: str | None = None
    status: str = "active"


@dataclass
class _FakeCmsPage:
    id: UUID
    tenant_id: UUID
    title: str
    slug: str
    body: str
    source_url: str | None
    status: str
    created_by: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class _UserRepo:
    def __init__(self, users):
        self._by_email = {u.email: u for u in users}

    async def get_by_email(self, email):
        return self._by_email.get(email)


class _CmsRepoFake:
    def __init__(self):
        self.rows: list[_FakeCmsPage] = []

    async def list_pages(self, tenant_id):
        return [p for p in self.rows if p.tenant_id == tenant_id]

    async def create(self, *, tenant_id, title, slug, body, source_url=None,
                     status="published", created_by=None):
        page = _FakeCmsPage(
            id=uuid4(), tenant_id=tenant_id, title=title, slug=slug,
            body=body, source_url=source_url, status=status, created_by=created_by,
        )
        self.rows.append(page)
        return page


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    monkeypatch.setenv("CONCIERGE_ENV", "prod")

    user_repo = _UserRepo([
        _FakeAdminUser(
            id=uuid4(),
            tenant_id=TENANT_A,
            email="alice@a.example",
            password_hash=hash_password("AlicePw1"),
        ),
    ])
    cms_repo = _CmsRepoFake()

    monkeypatch.setattr(admin_auth_route, "AdminUserRepository", lambda _s: user_repo)
    monkeypatch.setattr(cms_route, "CmsRepository", lambda _s: cms_repo)

    async def _no_db():
        yield None

    app.dependency_overrides[get_session] = _no_db
    try:
        with TestClient(app) as tc:
            yield tc, cms_repo
    finally:
        app.dependency_overrides.pop(get_session, None)


def _login(tc: TestClient) -> str:
    resp = tc.post("/admin/login", json={"email": "alice@a.example", "password": "AlicePw1"})
    assert resp.status_code == 200, resp.text
    return resp.json()["token"]


def test_create_uses_jwt_tenant_id(client) -> None:
    tc, repo = client
    token = _login(tc)
    resp = tc.post(
        "/cms/pages",
        headers={"Authorization": f"Bearer {token}"},
        json={"title": "Pricing", "slug": "pricing", "body": "Plans."},
    )
    assert resp.status_code == 201, resp.text
    saved = [p for p in repo.rows if p.slug == "pricing"]
    assert len(saved) == 1
    assert saved[0].tenant_id == TENANT_A  # JWT tenant, not anything from body
    assert saved[0].created_by == "alice@a.example"


def test_create_rejects_body_smuggled_tenant_id(client) -> None:
    """Even if the form mistakenly sends tenant_id, server returns 422."""
    tc, repo = client
    token = _login(tc)
    resp = tc.post(
        "/cms/pages",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "title": "Cross",
            "slug": "cross",
            "body": "b",
            "tenant_id": str(TENANT_B),  # forbidden extra
        },
    )
    assert resp.status_code == 422, resp.text
    # And nothing was persisted.
    assert all(p.slug != "cross" for p in repo.rows)


def test_create_without_admin_jwt_returns_403(client) -> None:
    tc, _ = client
    resp = tc.post("/cms/pages", json={"title": "x", "slug": "x", "body": "x"})
    assert resp.status_code == 403
