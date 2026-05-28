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
        """List CMS pages for one tenant only, newest first."""
        result = await self._session.execute(
            select(CmsPage)
            .where(CmsPage.tenant_id == tenant_id)
            .order_by(CmsPage.updated_at.desc())
        )
        return list(result.scalars().all())

    async def create(
        self,
        *,
        tenant_id: UUID,
        title: str,
        slug: str,
        body: str,
        source_url: str | None = None,
        status: str = "published",
        created_by: str | None = None,
    ) -> CmsPage:
        """Create one tenant-scoped CMS page.

        `tenant_id` MUST come from trusted server context (admin JWT). The
        route layer is responsible for ensuring it is never read from the
        request body.
        """
        page = CmsPage(
            tenant_id=tenant_id,
            title=title,
            slug=slug,
            body=body,
            source_url=source_url,
            status=status,
            created_by=created_by,
        )
        self._session.add(page)
        await self._session.flush()
        return page
