# Owner: Hiba
"""Unit tests for tenant management business rules."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.domain.tenant import PlatformRole, TenantStatus, UsageEvent, UsageFeature, UsageUnitType
from app.services.tenant_service import (
    TenantNotFoundError,
    TenantPermissionError,
    TenantService,
)


@dataclass
class FakeTenant:
    """Small tenant object compatible with Pydantic from_attributes."""

    name: str
    id: UUID = field(default_factory=uuid4)
    status: str = TenantStatus.ACTIVE.value
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass
class FakeRateLimit:
    """Small rate-limit object compatible with service expectations."""

    action: str
    limit_count: int
    window_seconds: int


class FakeTenantRepository:
    """In-memory repository double for service tests."""

    def __init__(self) -> None:
        self.tenant: FakeTenant | None = None
        self.created_names: list[str] = []
        self.audit_logs: list[dict[str, Any]] = []
        self.status_changes: list[str] = []
        self.usage_events: list[dict[str, Any]] = []
        self.rate_limits: dict[str, FakeRateLimit] = {}
        self.usage_counts: dict[str, int] = {}
        self.erasure_jobs: list[dict[str, Any]] = []
        self.erasure_counts = {
            "cms_pages": 2,
            "rag_chunks": 0,
            "leads": 1,
            "conversations": 1,
            "widget_configs": 0,
        }

    async def create(self, name: str) -> FakeTenant:
        """Create a fake tenant."""
        self.created_names.append(name)
        self.tenant = FakeTenant(name=name)
        return self.tenant

    async def get_by_id(self, tenant_id: UUID) -> FakeTenant | None:
        """Fetch a fake tenant by id."""
        if self.tenant is None or self.tenant.id != tenant_id:
            return None
        return self.tenant

    async def set_status(self, tenant_id: UUID, status: str) -> FakeTenant | None:
        """Update a fake tenant status."""
        if self.tenant is None or self.tenant.id != tenant_id:
            return None
        self.tenant.status = status
        self.tenant.updated_at = datetime.now(UTC)
        self.status_changes.append(status)
        return self.tenant

    async def add_audit_log(
        self,
        tenant_id: UUID,
        actor_role: str,
        action: str,
        actor_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        """Capture a fake audit event."""
        self.audit_logs.append(
            {
                "tenant_id": tenant_id,
                "actor_id": actor_id,
                "actor_role": actor_role,
                "action": action,
                "metadata": metadata or {},
            }
        )

    async def record_usage(
        self,
        tenant_id: UUID,
        feature: str,
        units: int,
        unit_type: str,
        estimated_cost_usd: float,
        trace_id: str | None = None,
    ) -> None:
        """Capture a fake usage event."""
        self.usage_events.append(
            {
                "tenant_id": tenant_id,
                "feature": feature,
                "units": units,
                "unit_type": unit_type,
                "estimated_cost_usd": estimated_cost_usd,
                "trace_id": trace_id,
            }
        )

    async def get_rate_limit(self, tenant_id: UUID, action: str) -> FakeRateLimit | None:
        """Fetch a fake rate-limit config."""
        if self.tenant is None or self.tenant.id != tenant_id:
            return None
        return self.rate_limits.get(action)

    async def count_usage_since(
        self,
        tenant_id: UUID,
        action: str,
        window_start: datetime,
    ) -> int:
        """Return a fake usage count for the configured window."""
        if self.tenant is None or self.tenant.id != tenant_id:
            return 0
        return self.usage_counts.get(action, 0)

    async def create_erasure_job(
        self,
        tenant_id: UUID,
        requested_by: str,
        status: str,
        deleted_counts: dict[str, int],
        started_at: datetime,
        completed_at: datetime | None = None,
    ) -> None:
        """Capture fake erasure job bookkeeping."""
        self.erasure_jobs.append(
            {
                "tenant_id": tenant_id,
                "requested_by": requested_by,
                "status": status,
                "deleted_counts": deleted_counts,
                "started_at": started_at,
                "completed_at": completed_at,
            }
        )

    async def erase_tenant_rows(self, tenant_id: UUID) -> dict[str, int]:
        """Return fake tenant-owned deletion counts."""
        if self.tenant is None or self.tenant.id != tenant_id:
            return {}
        return self.erasure_counts.copy()


@pytest.mark.asyncio
async def test_provision_tenant_requires_tenant_manager() -> None:
    """Tenant admins cannot perform platform provisioning."""
    repo = FakeTenantRepository()
    service = TenantService(repo)  # type: ignore[arg-type]

    with pytest.raises(TenantPermissionError):
        await service.provision_tenant("Acme", PlatformRole.TENANT_ADMIN, actor_id="user-1")

    assert repo.created_names == []
    assert repo.audit_logs == []


@pytest.mark.asyncio
async def test_provision_tenant_records_audit_log() -> None:
    """Provisioning creates a tenant and writes a tenant-scoped audit event."""
    repo = FakeTenantRepository()
    service = TenantService(repo)  # type: ignore[arg-type]

    tenant = await service.provision_tenant(
        "Acme",
        PlatformRole.TENANT_MANAGER,
        actor_id="hiba",
    )

    assert tenant.name == "Acme"
    assert tenant.status == TenantStatus.ACTIVE.value
    assert repo.audit_logs == [
        {
            "tenant_id": tenant.id,
            "actor_id": "hiba",
            "actor_role": PlatformRole.TENANT_MANAGER.value,
            "action": "tenant.provisioned",
            "metadata": {"tenant_name": "Acme"},
        }
    ]


@pytest.mark.asyncio
async def test_suspend_tenant_records_audit_log() -> None:
    """Suspension changes status and records a scoped audit event."""
    repo = FakeTenantRepository()
    service = TenantService(repo)  # type: ignore[arg-type]
    tenant = await service.provision_tenant("Acme", "tenant_manager", actor_id="hiba")

    suspended = await service.suspend_tenant(
        tenant.id,
        "tenant_manager",
        actor_id="hiba",
        reason="billing issue",
    )

    assert suspended.status == TenantStatus.SUSPENDED.value
    assert repo.audit_logs[-1] == {
        "tenant_id": tenant.id,
        "actor_id": "hiba",
        "actor_role": PlatformRole.TENANT_MANAGER.value,
        "action": "tenant.suspended",
        "metadata": {"reason": "billing issue"},
    }


@pytest.mark.asyncio
async def test_suspend_tenant_raises_when_tenant_missing() -> None:
    """Suspension refuses unknown tenant IDs."""
    repo = FakeTenantRepository()
    service = TenantService(repo)  # type: ignore[arg-type]

    with pytest.raises(TenantNotFoundError):
        await service.suspend_tenant(uuid4(), "tenant_manager", actor_id="hiba")

    assert repo.audit_logs == []


@pytest.mark.asyncio
async def test_erase_tenant_records_audit_log_and_deleted_counts() -> None:
    """Erasure moves status, records counts, and writes audit events."""
    repo = FakeTenantRepository()
    service = TenantService(repo)  # type: ignore[arg-type]
    tenant = await service.provision_tenant("Acme", "tenant_manager", actor_id="hiba")

    result = await service.erase_tenant(
        tenant.id,
        "tenant_manager",
        actor_id="hiba",
        reason="customer request",
    )

    assert result.tenant_id == tenant.id
    assert result.status == TenantStatus.ERASED.value
    assert result.deleted_rows == repo.erasure_counts
    assert result.trace_id.startswith("erase-")
    assert repo.status_changes[-2:] == [TenantStatus.ERASING.value, TenantStatus.ERASED.value]
    assert [event["action"] for event in repo.audit_logs[-2:]] == [
        "tenant.erasure_requested",
        "tenant.erased",
    ]
    assert repo.erasure_jobs[-1]["status"] == "completed"
    assert repo.erasure_jobs[-1]["deleted_counts"] == repo.erasure_counts


@pytest.mark.asyncio
async def test_erase_tenant_requires_tenant_manager() -> None:
    """Tenant admins cannot erase tenants."""
    repo = FakeTenantRepository()
    repo.tenant = FakeTenant(name="Acme")
    service = TenantService(repo)  # type: ignore[arg-type]

    with pytest.raises(TenantPermissionError):
        await service.erase_tenant(repo.tenant.id, PlatformRole.TENANT_ADMIN, actor_id="admin")

    assert repo.status_changes == []
    assert repo.audit_logs == []
    assert repo.erasure_jobs == []


@pytest.mark.asyncio
async def test_erase_tenant_raises_when_tenant_missing() -> None:
    """Erasure refuses unknown tenant IDs before audit bookkeeping."""
    repo = FakeTenantRepository()
    service = TenantService(repo)  # type: ignore[arg-type]

    with pytest.raises(TenantNotFoundError):
        await service.erase_tenant(uuid4(), "tenant_manager", actor_id="hiba")

    assert repo.audit_logs == []
    assert repo.erasure_jobs == []


@pytest.mark.asyncio
async def test_record_usage_writes_tenant_scoped_event() -> None:
    """Usage events are recorded only after the tenant exists."""
    repo = FakeTenantRepository()
    service = TenantService(repo)  # type: ignore[arg-type]
    tenant = await service.provision_tenant("Acme", "tenant_manager", actor_id="hiba")

    await service.record_usage(
        tenant.id,
        UsageEvent(
            feature=UsageFeature.CHAT,
            units=42,
            unit_type=UsageUnitType.TOKENS,
            estimated_cost_usd=0.12,
            trace_id="trace-1",
        ),
    )

    assert repo.usage_events == [
        {
            "tenant_id": tenant.id,
            "feature": UsageFeature.CHAT.value,
            "units": 42,
            "unit_type": UsageUnitType.TOKENS.value,
            "estimated_cost_usd": 0.12,
            "trace_id": "trace-1",
        }
    ]


@pytest.mark.asyncio
async def test_record_usage_raises_when_tenant_missing() -> None:
    """Usage events cannot be recorded for an unknown tenant."""
    repo = FakeTenantRepository()
    service = TenantService(repo)  # type: ignore[arg-type]

    with pytest.raises(TenantNotFoundError):
        await service.record_usage(
            uuid4(),
            UsageEvent(
                feature="chat",
                units=1,
                unit_type="requests",
                estimated_cost_usd=0,
            ),
        )

    assert repo.usage_events == []


@pytest.mark.asyncio
async def test_check_rate_limit_allows_when_no_limit_configured() -> None:
    """Missing rate-limit config leaves the tenant action allowed."""
    repo = FakeTenantRepository()
    service = TenantService(repo)  # type: ignore[arg-type]
    tenant = await service.provision_tenant("Acme", "tenant_manager", actor_id="hiba")

    result = await service.check_rate_limit(tenant.id, "chat")

    assert result.allowed is True
    assert result.limit_count is None
    assert result.remaining is None
    assert result.used == 0


@pytest.mark.asyncio
async def test_check_rate_limit_allows_under_limit() -> None:
    """Configured limits allow actions while usage remains below the limit."""
    repo = FakeTenantRepository()
    service = TenantService(repo)  # type: ignore[arg-type]
    tenant = await service.provision_tenant("Acme", "tenant_manager", actor_id="hiba")
    repo.rate_limits["chat"] = FakeRateLimit(action="chat", limit_count=3, window_seconds=60)
    repo.usage_counts["chat"] = 2

    result = await service.check_rate_limit(tenant.id, "chat")

    assert result.allowed is True
    assert result.used == 2
    assert result.remaining == 1
    assert result.window_seconds == 60
    assert repo.audit_logs[-1]["action"] == "tenant.provisioned"


@pytest.mark.asyncio
async def test_check_rate_limit_blocks_and_audits_when_limit_reached() -> None:
    """Configured limits block actions and audit once usage reaches the cap."""
    repo = FakeTenantRepository()
    service = TenantService(repo)  # type: ignore[arg-type]
    tenant = await service.provision_tenant("Acme", "tenant_manager", actor_id="hiba")
    repo.rate_limits["chat"] = FakeRateLimit(action="chat", limit_count=3, window_seconds=60)
    repo.usage_counts["chat"] = 3

    result = await service.check_rate_limit(tenant.id, "chat")

    assert result.allowed is False
    assert result.used == 3
    assert result.remaining == 0
    assert repo.audit_logs[-1] == {
        "tenant_id": tenant.id,
        "actor_id": "system",
        "actor_role": "system",
        "action": "tenant.rate_limited",
        "metadata": {
            "action": "chat",
            "used": 3,
            "limit_count": 3,
            "window_seconds": 60,
        },
    }
