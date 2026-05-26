# Owner: Hiba
"""CMS repository.

All CMS queries must be scoped by tenant_id.
"""

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CmsPage


class CmsRepository:
    """SQL operations for CMS pages."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_pages(self, tenant_id: UUID) -> list[CmsPage]:
        """List CMS pages for one tenant only."""
        result = await self._session.execute(select(CmsPage).where(CmsPage.tenant_id == tenant_id))
        return list(result.scalars().all())
