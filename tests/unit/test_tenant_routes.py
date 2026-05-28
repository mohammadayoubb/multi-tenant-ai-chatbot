# Owner: Hiba
"""Tests for Hiba tenant management routes."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.deps import PlatformActor, get_platform_actor, get_tenant_service
from app.api.routes.tenants import router
from app.domain.tenant import ErasureResult, PlatformRole, RateLimitResult, TenantStatus, UsageEvent


@dataclass
class FakeTenantDomain:
    """Small tenant object compatible with response schemas."""

    name: str
    id: UUID = field(default_factory=uuid4)
    status: str = TenantStatus.ACTIVE.value
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class FakeTenantService:
    """Route-level service double."""

    def __init__(self) -> None:
        self.tenant = FakeTenantDomain(name="Acme")
        self.usage_events: list[UsageEvent] = []

    async def provision_tenant(
        self,
        name: str,
        actor_role: PlatformRole | str,
        actor_id: str | None = None,
    ) -> FakeTenantDomain:
        """Fake tenant provisioning."""
        self.tenant = FakeTenantDomain(name=name)
        return self.tenant

    async def get_tenant(
        self,
        tenant_id: UUID,
        actor_role: PlatformRole | str,
    ) -> FakeTenantDomain:
        """Fake tenant metadata lookup."""
        self.tenant.id = tenant_id
        return self.tenant

    async def suspend_tenant(
        self,
        tenant_id: UUID,
        actor_role: PlatformRole | str,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> FakeTenantDomain:
        """Fake tenant suspension."""
        self.tenant.id = tenant_id
        self.tenant.status = TenantStatus.SUSPENDED.value
        return self.tenant

    async def erase_tenant(
        self,
        tenant_id: UUID,
        actor_role: PlatformRole | str,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> ErasureResult:
        """Fake tenant erasure."""
        return ErasureResult(
            tenant_id=tenant_id,
            status=TenantStatus.ERASED.value,
            deleted_rows={
                "cms_pages": 0,
                "rag_chunks": 0,
                "leads": 0,
                "conversations": 0,
                "widget_configs": 0,
            },
            deleted_blobs=0,
            deleted_sessions=0,
            trace_id="trace-1",
        )

    async def record_usage(self, tenant_id: UUID, usage: UsageEvent) -> None:
        """Fake usage recording."""
        self.usage_events.append(usage)

    async def check_rate_limit(self, tenant_id: UUID, action: str) -> RateLimitResult:
        """Fake rate-limit check."""
        return RateLimitResult(
            tenant_id=tenant_id,
            action=action,
            allowed=True,
            limit_count=10,
            used=3,
            remaining=7,
            window_seconds=60,
        )


def test_tenant_routes_use_schema_and_dependency_wiring() -> None:
    """Tenant routes call the injected Hiba service and serialize schemas."""
    service = FakeTenantService()
    client = _build_client(service)

    created = client.post("/tenants", json={"name": "Acme"}).json()
    tenant_id = created["id"]
    fetched = client.get(f"/tenants/{tenant_id}").json()
    suspended = client.post(
        f"/tenants/{tenant_id}/suspend",
        json={"reason": "billing"},
    ).json()
    erased = client.request(
        "DELETE",
        f"/tenants/{tenant_id}",
        json={"reason": "customer request"},
    ).json()
    usage_response = client.post(
        f"/tenants/{tenant_id}/usage",
        json={
            "feature": "chat",
            "units": 4,
            "unit_type": "requests",
            "estimated_cost_usd": 0.01,
            "trace_id": "trace-usage",
        },
    )
    rate_limit = client.get(f"/tenants/{tenant_id}/rate-limit/chat").json()

    assert created["name"] == "Acme"
    assert fetched["id"] == tenant_id
    assert suspended["status"] == TenantStatus.SUSPENDED.value
    assert erased["status"] == TenantStatus.ERASED.value
    assert usage_response.status_code == 204
    assert service.usage_events[0].feature == "chat"
    assert rate_limit["remaining"] == 7


def _build_client(service: FakeTenantService) -> TestClient:
    """Build a route-only FastAPI test client with dependency overrides."""
    app = FastAPI()
    app.include_router(router)
    app.dependency_overrides[get_platform_actor] = lambda: PlatformActor(
        actor_id="hiba",
        actor_role=PlatformRole.TENANT_MANAGER,
    )
    app.dependency_overrides[get_tenant_service] = lambda: service
    return TestClient(app)
