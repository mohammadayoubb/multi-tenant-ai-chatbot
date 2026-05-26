# Owner: Hiba
"""Tenant service.

Business rules for tenant provisioning, suspension, and erasure live here.
"""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from app.domain.tenant import (
    ErasureResult,
    PlatformRole,
    RateLimitResult,
    TenantDomain,
    TenantStatus,
    UsageEvent,
    UsageFeature,
    UsageUnitType,
)
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

    async def erase_tenant(
        self,
        tenant_id: UUID,
        actor_role: PlatformRole | str,
        actor_id: str | None = None,
        reason: str | None = None,
    ) -> ErasureResult:
        """Erase tenant-owned rows and audit the destructive platform action."""
        role = self._require_tenant_manager(actor_role)
        trace_id = f"erase-{uuid4()}"
        started_at = datetime.now(UTC)

        tenant = await self._repo.set_status(tenant_id, TenantStatus.ERASING.value)
        if tenant is None:
            raise TenantNotFoundError(f"Tenant {tenant_id} was not found")

        await self._repo.add_audit_log(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_role=role.value,
            action="tenant.erasure_requested",
            metadata={"reason": reason, "trace_id": trace_id},
        )
        deleted_rows = await self._repo.erase_tenant_rows(tenant_id)
        completed_at = datetime.now(UTC)
        await self._repo.create_erasure_job(
            tenant_id=tenant_id,
            requested_by=actor_id or "unknown",
            status="completed",
            deleted_counts=deleted_rows,
            started_at=started_at,
            completed_at=completed_at,
        )

        erased_tenant = await self._repo.set_status(tenant_id, TenantStatus.ERASED.value)
        if erased_tenant is None:
            raise TenantNotFoundError(f"Tenant {tenant_id} was not found")

        await self._repo.add_audit_log(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_role=role.value,
            action="tenant.erased",
            metadata={"deleted_rows": deleted_rows, "trace_id": trace_id},
        )
        return ErasureResult(
            tenant_id=tenant_id,
            status=TenantStatus.ERASED.value,
            deleted_rows=deleted_rows,
            deleted_blobs=0,
            deleted_sessions=0,
            trace_id=trace_id,
        )

    async def record_usage(self, tenant_id: UUID, usage: UsageEvent) -> None:
        """Record one tenant-scoped usage event for attribution."""
        await self._require_tenant_exists(tenant_id)
        await self._repo.record_usage(
            tenant_id=tenant_id,
            feature=self._usage_feature_value(usage.feature),
            units=usage.units,
            unit_type=self._usage_unit_type_value(usage.unit_type),
            estimated_cost_usd=usage.estimated_cost_usd,
            trace_id=usage.trace_id,
        )

    async def check_rate_limit(self, tenant_id: UUID, action: str) -> RateLimitResult:
        """Check whether a tenant is still inside the configured action limit."""
        await self._require_tenant_exists(tenant_id)
        rate_limit = await self._repo.get_rate_limit(tenant_id, action)
        if rate_limit is None:
            return RateLimitResult(
                tenant_id=tenant_id,
                action=action,
                allowed=True,
                limit_count=None,
                used=0,
                remaining=None,
                window_seconds=None,
            )

        window_start = datetime.now(UTC) - timedelta(seconds=rate_limit.window_seconds)
        used = await self._repo.count_usage_since(tenant_id, action, window_start)
        allowed = used < rate_limit.limit_count
        remaining = max(rate_limit.limit_count - used, 0)
        if not allowed:
            await self._repo.add_audit_log(
                tenant_id=tenant_id,
                actor_id="system",
                actor_role="system",
                action="tenant.rate_limited",
                metadata={
                    "action": action,
                    "used": used,
                    "limit_count": rate_limit.limit_count,
                    "window_seconds": rate_limit.window_seconds,
                },
            )

        return RateLimitResult(
            tenant_id=tenant_id,
            action=action,
            allowed=allowed,
            limit_count=rate_limit.limit_count,
            used=used,
            remaining=remaining,
            window_seconds=rate_limit.window_seconds,
        )

    def _require_tenant_manager(self, actor_role: PlatformRole | str) -> PlatformRole:
        """Ensure only tenant managers can perform platform tenant actions."""
        try:
            role = PlatformRole(actor_role)
        except ValueError as exc:
            raise TenantPermissionError("Only tenant_manager can manage tenants") from exc
        if role is not PlatformRole.TENANT_MANAGER:
            raise TenantPermissionError("Only tenant_manager can manage tenants")
        return role

    async def _require_tenant_exists(self, tenant_id: UUID) -> None:
        """Ensure a target tenant exists before writing platform accounting data."""
        tenant = await self._repo.get_by_id(tenant_id)
        if tenant is None:
            raise TenantNotFoundError(f"Tenant {tenant_id} was not found")

    def _usage_feature_value(self, feature: UsageFeature | str) -> str:
        """Normalize usage feature enum values for persistence."""
        if isinstance(feature, UsageFeature):
            return feature.value
        return feature

    def _usage_unit_type_value(self, unit_type: UsageUnitType | str) -> str:
        """Normalize usage unit type enum values for persistence."""
        if isinstance(unit_type, UsageUnitType):
            return unit_type.value
        return unit_type
