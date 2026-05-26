# Owner: Hiba
"""Unit tests for tenant management business rules."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.domain.tenant import PlatformRole, TenantStatus
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


class FakeTenantRepository:
    """In-memory repository double for service tests."""

    def __init__(self) -> None:
        self.tenant: FakeTenant | None = None
        self.created_names: list[str] = []
        self.audit_logs: list[dict[str, Any]] = []

    async def create(self, name: str) -> FakeTenant:
        """Create a fake tenant."""
        self.created_names.append(name)
        self.tenant = FakeTenant(name=name)
        return self.tenant

    async def set_status(self, tenant_id: UUID, status: str) -> FakeTenant | None:
        """Update a fake tenant status."""
        if self.tenant is None or self.tenant.id != tenant_id:
            return None
        self.tenant.status = status
        self.tenant.updated_at = datetime.now(UTC)
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
