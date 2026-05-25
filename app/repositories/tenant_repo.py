# Owner: Hiba
"""Tenant repository.

Repositories contain SQL only and must keep tenant boundaries explicit.
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tenant


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

    async def get_by_id(self, tenant_id: int) -> Tenant | None:
        """Fetch tenant by id."""
        result = await self._session.execute(select(Tenant).where(Tenant.id == tenant_id))
        return result.scalar_one_or_none()
