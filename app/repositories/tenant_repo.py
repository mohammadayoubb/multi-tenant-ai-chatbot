# Owner: Hiba
"""Tenant repository.

Repositories contain SQL only and must keep tenant boundaries explicit.
"""

import re
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import case, cast, delete, func, select
from sqlalchemy.dialects.postgresql import DATE
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
        """Create a tenant.

        Derives `slug` from `name` using the same regex Decision 14's
        migration backfill applied (LOWER + non-alphanumeric → '-'). Without
        this every call would violate the slug NOT NULL constraint.
        """
        slug = re.sub(r"[^a-zA-Z0-9]+", "-", name).lower().strip("-")
        tenant = Tenant(name=name, slug=slug)
        self._session.add(tenant)
        await self._session.flush()
        return tenant

    async def get_by_id(self, tenant_id: UUID) -> Tenant | None:
        """Fetch tenant by id."""
        result = await self._session.execute(select(Tenant).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()

    async def get_by_name(self, name: str) -> Tenant | None:
        """Fetch tenant by unique name."""
        result = await self._session.execute(select(Tenant).where(Tenant.name == name))
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

    async def list_all(self) -> list[Tenant]:
        """List every tenant (TM-scope read; route enforces the role check)."""
        result = await self._session.execute(
            select(Tenant).order_by(Tenant.created_at.desc())
        )
        return list(result.scalars().all())

    async def list_audit_logs_platform_scope(
        self,
        *,
        actor: str | None = None,
        tenant_id: UUID | None = None,
        action: str | None = None,
        date_from: str | None = None,
        date_to: str | None = None,
    ) -> list[AuditLog]:
        """List audit events across every tenant (TM-scope; role checked at route).

        Each filter is optional. `date_from` / `date_to` accept ISO-8601 strings;
        malformed values are ignored rather than raising — the UI never sends
        them malformed (the filter form gates them).
        """
        from datetime import datetime as _dt

        stmt = select(AuditLog)
        if actor:
            stmt = stmt.where(AuditLog.actor_id == actor)
        if tenant_id is not None:
            stmt = stmt.where(AuditLog.tenant_id == tenant_id)
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if date_from:
            try:
                stmt = stmt.where(AuditLog.created_at >= _dt.fromisoformat(date_from))
            except ValueError:
                pass
        if date_to:
            try:
                stmt = stmt.where(AuditLog.created_at <= _dt.fromisoformat(date_to))
            except ValueError:
                pass
        stmt = stmt.order_by(AuditLog.created_at.desc()).limit(500)
        result = await self._session.execute(stmt)
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

    async def upsert_rate_limit(
        self,
        tenant_id: UUID,
        action: str,
        limit_count: int,
        window_seconds: int,
    ) -> TenantRateLimit:
        """Create or update one tenant-scoped rate-limit configuration."""
        async with self._tenant_context(tenant_id):
            result = await self._session.execute(
                select(TenantRateLimit).where(
                    TenantRateLimit.tenant_id == tenant_id,
                    TenantRateLimit.action == action,
                )
            )
            rate_limit = result.scalar_one_or_none()
            if rate_limit is None:
                rate_limit = TenantRateLimit(
                    tenant_id=tenant_id,
                    action=action,
                    limit_count=limit_count,
                    window_seconds=window_seconds,
                )
                self._session.add(rate_limit)
            else:
                rate_limit.limit_count = limit_count
                rate_limit.window_seconds = window_seconds
            await self._session.flush()
        return rate_limit

    async def usage_rollup(
        self,
        tenant_id: UUID,
        *,
        since: datetime,
    ) -> dict[str, Any]:
        """Return a dashboard-shaped rollup of usage rows since `since`.

        Returned shape matches what admin/usage_page.py expects:
            {
              "total_tokens":   int,
              "total_cost_usd": float,
              "by_feature":     {feature: {"tokens": int, "cost_usd": float}},
              "daily_cost_usd": [{"date": "YYYY-MM-DD", "cost_usd": float}],
            }
        Tenant-scoped (CONTRACT.md §7) — the WHERE on tenant_id is explicit.
        """
        async with self._tenant_context(tenant_id):
            # Totals: tokens are units where unit_type='tokens'; cost is sum
            # of estimated_cost_usd over every row regardless of unit_type.
            totals_result = await self._session.execute(
                select(
                    func.coalesce(
                        func.sum(
                            case(
                                (TenantUsage.unit_type == "tokens", TenantUsage.units),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("total_tokens"),
                    func.coalesce(
                        func.sum(TenantUsage.estimated_cost_usd), 0
                    ).label("total_cost_usd"),
                ).where(
                    TenantUsage.tenant_id == tenant_id,
                    TenantUsage.created_at >= since,
                )
            )
            totals_row = totals_result.one()

            # Per-feature breakdown
            by_feature_rows = await self._session.execute(
                select(
                    TenantUsage.feature,
                    func.coalesce(
                        func.sum(
                            case(
                                (TenantUsage.unit_type == "tokens", TenantUsage.units),
                                else_=0,
                            )
                        ),
                        0,
                    ).label("tokens"),
                    func.coalesce(
                        func.sum(TenantUsage.estimated_cost_usd), 0
                    ).label("cost_usd"),
                )
                .where(
                    TenantUsage.tenant_id == tenant_id,
                    TenantUsage.created_at >= since,
                )
                .group_by(TenantUsage.feature)
            )
            by_feature: dict[str, dict[str, float | int]] = {}
            for row in by_feature_rows:
                by_feature[row.feature] = {
                    "tokens": int(row.tokens or 0),
                    "cost_usd": float(row.cost_usd or 0.0),
                }

            # Daily cost series (ordered)
            day_col = cast(TenantUsage.created_at, DATE).label("day")
            daily_rows = await self._session.execute(
                select(
                    day_col,
                    func.coalesce(
                        func.sum(TenantUsage.estimated_cost_usd), 0
                    ).label("cost_usd"),
                )
                .where(
                    TenantUsage.tenant_id == tenant_id,
                    TenantUsage.created_at >= since,
                )
                .group_by(day_col)
                .order_by(day_col)
            )
            daily = [
                {"date": row.day.isoformat(), "cost_usd": float(row.cost_usd or 0.0)}
                for row in daily_rows
            ]

        return {
            "total_tokens": int(totals_row.total_tokens or 0),
            "total_cost_usd": float(totals_row.total_cost_usd or 0.0),
            "by_feature": by_feature,
            "daily_cost_usd": daily,
        }

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
