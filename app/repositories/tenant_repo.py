# Owner: Hiba
"""Tenant repository.

Repositories contain SQL only and must keep tenant boundaries explicit.
"""

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AuditLog, Tenant


class TenantRepository:
    """SQL operations for tenants."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, name: str) -> Tenant:
        """Create a tenant."""
        tenant = Tenant(name=name)
        self._session.add(tenant)
        await self._session.flush()
        return tenant

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        """Fetch tenant by id."""
        result = await self._session.execute(select(Tenant).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    async def set_status(self, tenant_id: UUID, status: str) -> Tenant | None:
        """Update one tenant's lifecycle status."""
        tenant = await self.get_by_id(tenant_id)
        if tenant is None:
            return None
        tenant.status = status
        await self._session.flush()
        return tenant

    async def add_audit_log(
        self,
        tenant_id: UUID,
        actor_role: str,
        action: str,
        actor_id: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AuditLog:
        """Record an audit event scoped to the affected tenant."""
        audit_log = AuditLog(
            tenant_id=tenant_id,
            actor_id=actor_id,
            actor_role=actor_role,
            action=action,
            metadata_json=metadata or {},
        )
        self._session.add(audit_log)
        await self._session.flush()
        return audit_log

    async def list_audit_logs(self, tenant_id: UUID) -> list[AuditLog]:
        """List audit events for one tenant only."""
        result = await self._session.execute(
            select(AuditLog)
            .where(AuditLog.tenant_id == tenant_id)
            .order_by(AuditLog.created_at.desc())
        )
        return list(result.scalars().all())
