# Owner: Amer
"""End-to-end admin auth flow:
   1. POST /admin/login (with a seeded admin row injected via dep override)
   2. POST /widgets/config using ONLY the returned JWT — no dev headers

Confirms the JWT path through `require_tenant_admin` works in production-mode
(CONCIERGE_ENV != dev) where the dev-header fallback is closed.
"""

from __future__ import annotations

from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from fastapi.testclient import TestClient

import app.api.routes.widgets as widgets_route
from app.api.routes import admin_auth as admin_auth_route
from app.db.session import get_session
from app.domain.widget import WidgetConfigDomain
from app.infra.password import hash_password
from app.main import app
from app.repositories.widget_repo import InMemoryWidgetRepository
from app.services.widget_service import WidgetConfigService

TENANT_ID = UUID("33333333-3333-3333-3333-333333333333")
WIDGET_ID = UUID("c0ffee00-c0ff-ee00-c0ff-ee00c0ffee00")
ROW_ID = uuid4()


@dataclass
class _FakeUser:
    id: UUID
    tenant_id: UUID
    email: str
    password_hash: str
    role: str = "tenant_admin"


class _FakeAdminUserRepo:
    """In-memory AdminUserRepository for the login route."""

    def __init__(self, users: list[_FakeUser]) -> None:
        self._by_email = {u.email: u for u in users}

    async def get_by_email(self, email: str):  # noqa: ANN201 — duck-typed
        return self._by_email.get(email)


def _seeded_widget_repo() -> InMemoryWidgetRepository:
    repo = InMemoryWidgetRepository()
    repo.clear()
    repo.upsert(
        WidgetConfigDomain(
            id=ROW_ID,
            tenant_id=TENANT_ID,
            widget_id=WIDGET_ID,
            allowed_origins=["https://acme.example"],
            enabled=True,
            tenant_status="active",
            theme_json=None,
            greeting=None,
        )
    )
    return repo


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch):
    """Production-mode app with one seeded admin and one widget row."""
    monkeypatch.setenv("CONCIERGE_ENV", "prod")  # closes the dev-headers door

    fake_repo = _FakeAdminUserRepo(
        [
            _FakeUser(
                id=uuid4(),
                tenant_id=TENANT_ID,
                email="alice@acme.example",
                password_hash=hash_password("s3cret-pw"),
            )
        ]
    )
    monkeypatch.setattr(
        admin_auth_route,
        "AdminUserRepository",
        lambda _session: fake_repo,
    )

    # In-memory get_session so login works without a real DB.
    async def _no_db():
        yield None

    app.dependency_overrides[get_session] = _no_db

    # Override the widget config service so the admin PUT exercises the real
    # `require_tenant_admin` JWT path against an in-memory backend.
    widget_repo = _seeded_widget_repo()
    audit_calls: list[dict] = []

    class _AuditCapture:
        async def add_audit_log(self, **kwargs):
            audit_calls.append(kwargs)

    def override_get_widget_config_service():
        return WidgetConfigService(repo=widget_repo, audit_logger=_AuditCapture())

    app.dependency_overrides[widgets_route.get_widget_config_service] = (
        override_get_widget_config_service
    )

    try:
        with TestClient(app) as tc:
            yield tc, audit_calls
    finally:
        app.dependency_overrides.pop(get_session, None)
        app.dependency_overrides.pop(widgets_route.get_widget_config_service, None)


def test_login_then_authenticated_widget_config_get_succeeds(client) -> None:
    tc, _ = client
    login = tc.post(
        "/admin/login",
        json={"email": "alice@acme.example", "password": "s3cret-pw"},
    )
    assert login.status_code == 200, login.text
    body = login.json()
    token = body["token"]
    assert body["tenant_id"] == str(TENANT_ID)
    assert body["role"] == "tenant_admin"

    # Use ONLY the JWT — no X-Concierge-* headers. dev-header fallback is
    # closed in this test because CONCIERGE_ENV=prod.
    cfg = tc.get(
        "/widgets/config", headers={"Authorization": f"Bearer {token}"}
    )
    assert cfg.status_code == 200, cfg.text
    assert cfg.json()["widget_id"] == str(WIDGET_ID)


def test_login_wrong_password_returns_401_with_canonical_body(client) -> None:
    tc, _ = client
    resp = tc.post(
        "/admin/login",
        json={"email": "alice@acme.example", "password": "WRONG"},
    )
    assert resp.status_code == 401
    assert resp.content == b'{"error":"invalid_credentials"}'


def test_login_unknown_email_returns_same_401(client) -> None:
    """Unknown email must look identical to wrong password (no enumeration)."""
    tc, _ = client
    resp = tc.post(
        "/admin/login",
        json={"email": "nobody@example.com", "password": "anything"},
    )
    assert resp.status_code == 401
    assert resp.content == b'{"error":"invalid_credentials"}'


def test_admin_call_without_jwt_in_prod_mode_returns_403(client) -> None:
    """Dev-header fallback must be inactive when CONCIERGE_ENV != dev."""
    tc, _ = client
    resp = tc.get(
        "/widgets/config",
        headers={
            "X-Concierge-Role": "tenant_admin",
            "X-Concierge-Tenant-Id": str(TENANT_ID),
            "X-Concierge-Actor-Id": "spoof@example.com",
        },
    )
    assert resp.status_code == 403


def test_admin_put_via_jwt_writes_audit_via_logger(client) -> None:
    """Full path: login → JWT → PUT /widgets/config → audit_logger called."""
    tc, audit_calls = client
    login = tc.post(
        "/admin/login",
        json={"email": "alice@acme.example", "password": "s3cret-pw"},
    )
    token = login.json()["token"]

    put = tc.put(
        "/widgets/config",
        headers={"Authorization": f"Bearer {token}"},
        json={
            "allowed_origins": ["https://acme.example", "https://acme.test"],
            "enabled": True,
            "theme_json": None,
            "greeting": None,
        },
    )
    assert put.status_code == 200, put.text
    assert any(
        c.get("action") == "widget.origin_added"
        and c.get("metadata", {}).get("origin") == "https://acme.test"
        for c in audit_calls
    )
