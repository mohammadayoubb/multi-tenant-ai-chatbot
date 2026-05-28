# Owner: Amer
"""Route tests for tenant-admin signup and login."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

import app.api.routes.auth as auth_route
from app.api.deps import get_tenant_service
from app.domain.tenant import TenantDomain
from app.repositories.widget_repo import InMemoryWidgetRepository
from app.services.admin_auth import InMemoryAdminAccountRepository


@dataclass
class FakeTenantService:
    """Small tenant service double for signup route tests."""

    created: list[TenantDomain] = field(default_factory=list)

    async def create_tenant(self, name: str) -> TenantDomain:
        tenant = TenantDomain(
            id=uuid4(),
            name=name,
            status="active",
            created_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )
        self.created.append(tenant)
        return tenant


def test_signup_returns_session_and_bootstraps_widget(monkeypatch) -> None:
    service = FakeTenantService()
    accounts = InMemoryAdminAccountRepository()
    widgets = InMemoryWidgetRepository()
    widgets.clear()

    client = _build_client(monkeypatch, service, accounts, widgets)

    signup = client.post(
        "/auth/signup",
        json={
            "business_name": "Acme Co",
            "email": "owner@acme.example",
            "password": "strong-password",
        },
    )

    assert signup.status_code == 201, signup.text
    payload = signup.json()
    assert payload["tenant_name"] == "Acme Co"
    assert UUID(payload["tenant_id"])
    assert UUID(payload["widget_id"])

    me = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {payload['access_token']}"},
    )
    assert me.status_code == 200
    assert me.json()["actor_id"] == "owner@acme.example"


def test_login_rejects_wrong_password(monkeypatch) -> None:
    service = FakeTenantService()
    accounts = InMemoryAdminAccountRepository()
    widgets = InMemoryWidgetRepository()
    widgets.clear()

    client = _build_client(monkeypatch, service, accounts, widgets)
    client.post(
        "/auth/signup",
        json={
            "business_name": "Bravo Co",
            "email": "owner@bravo.example",
            "password": "correct-horse",
        },
    )

    response = client.post(
        "/auth/login",
        json={
            "email": "owner@bravo.example",
            "password": "wrong-password",
        },
    )

    assert response.status_code == 401


def _build_client(
    monkeypatch,
    tenant_service: FakeTenantService,
    accounts: InMemoryAdminAccountRepository,
    widgets: InMemoryWidgetRepository,
) -> TestClient:
    app = FastAPI()
    app.include_router(auth_route.router)
    app.dependency_overrides[get_tenant_service] = lambda: tenant_service
    monkeypatch.setattr(auth_route, "get_admin_account_repository", lambda: accounts)
    monkeypatch.setattr(auth_route, "get_widget_repository", lambda: widgets)
    return TestClient(app)
