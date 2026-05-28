# Owner: Nasser
"""Lead repository.

The capture_lead tool writes through this repository.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Lead


class LeadRepository:
    """SQL operations for captured leads."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, tenant_id: int, name: str | None, contact: str | None, intent: str) -> Lead:
        """Create a tenant-scoped lead."""
        lead = Lead(tenant_id=tenant_id, name=name, contact=contact, intent=intent)
        self._session.add(lead)
        await self._session.flush()
        return lead

    async def list_by_tenant(self, tenant_id: UUID, *, limit: int = 100) -> list[Lead]:
        """Return up to `limit` leads for one tenant, newest first.

        Tenant-scoped (CONTRACT.md §7) — the WHERE clause must remain even
        after RLS lands so the filter is explicit in code and audit-grep-able.
        """
        result = await self._session.execute(
            select(Lead)
            .where(Lead.tenant_id == tenant_id)
            .order_by(Lead.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())
