# Owner: Hiba
"""Tenant repository.

Repositories contain SQL only and must keep tenant boundaries explicit.
"""

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.rls import reset_tenant_context, set_tenant_context
from app.db.models import (
    AuditLog,
    CmsPage,
    Conversation,
    ErasureJob,
    Lead,
    Tenant,
    TenantRateLimit,
    TenantUsage,
)


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
        async with self._tenant_context(tenant_id):
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
        async with self._tenant_context(tenant_id):
            result = await self._session.execute(
                select(AuditLog)
                .where(AuditLog.tenant_id == tenant_id)
                .order_by(AuditLog.created_at.desc())
            )
        return list(result.scalars().all())

    async def record_usage(
        self,
        tenant_id: UUID,
        feature: str,
        units: int,
        unit_type: str,
        estimated_cost_usd: float,
        trace_id: str | None = None,
    ) -> TenantUsage:
        """Record one tenant-scoped usage event."""
        async with self._tenant_context(tenant_id):
            usage = TenantUsage(
                tenant_id=tenant_id,
                feature=feature,
                units=units,
                unit_type=unit_type,
                estimated_cost_usd=estimated_cost_usd,
                trace_id=trace_id,
            )
            self._session.add(usage)
            await self._session.flush()
        return usage

    async def get_rate_limit(self, tenant_id: UUID, action: str) -> TenantRateLimit | None:
        """Fetch one tenant-scoped rate-limit configuration."""
        async with self._tenant_context(tenant_id):
            result = await self._session.execute(
                select(TenantRateLimit).where(
                    TenantRateLimit.tenant_id == tenant_id,
                    TenantRateLimit.action == action,
                )
            )
        return result.scalar_one_or_none()

    async def count_usage_since(self, tenant_id: UUID, action: str, window_start: datetime) -> int:
        """Count tenant usage units for an action since a window start."""
        async with self._tenant_context(tenant_id):
            result = await self._session.execute(
                select(func.coalesce(func.sum(TenantUsage.units), 0)).where(
                    TenantUsage.tenant_id == tenant_id,
                    TenantUsage.feature == action,
                    TenantUsage.created_at >= window_start,
                )
            )
        return int(result.scalar_one())

    async def create_erasure_job(
        self,
        tenant_id: UUID,
        requested_by: str,
        status: str,
        deleted_counts: dict[str, int],
        started_at: datetime,
        completed_at: datetime | None = None,
    ) -> ErasureJob:
        """Record tenant erasure job bookkeeping."""
        async with self._tenant_context(tenant_id):
            erasure_job = ErasureJob(
                tenant_id=tenant_id,
                requested_by=requested_by,
                status=status,
                deleted_counts_json=deleted_counts,
                started_at=started_at,
                completed_at=completed_at,
            )
            self._session.add(erasure_job)
            await self._session.flush()
        return erasure_job

    async def erase_tenant_rows(self, tenant_id: UUID) -> dict[str, int]:
        """Delete tenant-owned rows that this service currently owns."""
        async with self._tenant_context(tenant_id):
            leads = await self._delete_tenant_rows(Lead, tenant_id)
            conversations = await self._delete_tenant_rows(Conversation, tenant_id)
            cms_pages = await self._delete_tenant_rows(CmsPage, tenant_id)
        return {
            "cms_pages": cms_pages,
            "rag_chunks": 0,
            "leads": leads,
            "conversations": conversations,
            "widget_configs": 0,
        }

    async def _delete_tenant_rows(self, model: type[Any], tenant_id: UUID) -> int:
        """Delete tenant-scoped rows for one ORM model and return the affected count."""
        result: Any = await self._session.execute(delete(model).where(model.tenant_id == tenant_id))
        return int(result.rowcount or 0)

    @asynccontextmanager
    async def _tenant_context(self, tenant_id: UUID) -> AsyncIterator[None]:
        """Apply and reset the Postgres tenant context around tenant-owned queries."""
        await set_tenant_context(self._session, tenant_id)
        try:
            yield
        finally:
            await reset_tenant_context(self._session)
