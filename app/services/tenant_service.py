# Owner: Hiba
"""Tenant service.

Business rules for tenant provisioning, suspension, and erasure live here.
"""

from uuid import UUID

from app.domain.tenant import PlatformRole, TenantDomain, TenantStatus
from app.repositories.tenant_repo import TenantRepository


class TenantPermissionError(Exception):
    """Raised when an actor is not allowed to manage tenants."""


class TenantNotFoundError(Exception):
    """Raised when a tenant management action targets an unknown tenant."""


class TenantService:
    """Tenant business logic."""

    def __init__(self, repo: TenantRepository) -> None:
        self._repo = repo

    async def create_tenant(self, name: str) -> TenantDomain:
        """Create a tenant for internal scripts and tests."""
        return await self.provision_tenant(
            name=name,
            actor_role=PlatformRole.TENANT_MANAGER,
            actor_id="system",
        )

    async def provision_tenant(
        self,
        name: str,
        actor_role: PlatformRole | str,
        actor_id: str | None = None,
    ) -> TenantDomain:
        """Provision a tenant and audit the platform action."""
        role = self._require_tenant_manager(actor_role)
        tenant = await self._repo.create(name)
        await self._repo.add_audit_log(
            tenant_id=tenant.id,
            actor_id=actor_id,
            actor_role=role.value,
            action="tenant.provisioned",
            metadata={"tenant_name": name},
        )
        return TenantDomain.model_validate(tenant)

    async def suspend_tenant(
        self,
        tenant_id: UUID,
        actor_role: PlatformRole | str,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> TenantDomain:
        """Suspend a tenant and audit the platform action."""
        role = self._require_tenant_manager(actor_role)
        tenant = await self._repo.set_status(tenant_id, TenantStatus.SUSPENDED.value)
        if tenant is None:
            raise TenantNotFoundError(f"Tenant {tenant_id} was not found")

        await self._repo.add_audit_log(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_role=role.value,
            action="tenant.suspended",
            metadata={"reason": reason} if reason else {},
        )
        return TenantDomain.model_validate(tenant)

    def _require_tenant_manager(self, actor_role: PlatformRole | str) -> PlatformRole:
        """Ensure only tenant managers can perform platform tenant actions."""
        try:
            role = PlatformRole(actor_role)
        except ValueError as exc:
            raise TenantPermissionError("Only tenant_manager can manage tenants") from exc
        if role is not PlatformRole.TENANT_MANAGER:
            raise TenantPermissionError("Only tenant_manager can manage tenants")
        return role
