# Owner: Hiba
"""CMS repository.

All CMS queries must be scoped by tenant_id.
"""

from typing import Any
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

    async def get(self, page_id: UUID) -> CmsPage | None:
        """Lookup one CMS page by id, regardless of tenant.

        The tenant-scope check happens at the service layer so the route can
        return a single 403 body for "not yours" while still distinguishing
        "unknown id" with a 404.
        """
        result = await self._session.execute(
            select(CmsPage).where(CmsPage.id == page_id)
        )
        return result.scalar_one_or_none()

    async def update(
        self,
        page_id: UUID,
        tenant_id: UUID,
        body: dict[str, Any],
    ) -> CmsPage | None:
        """Tenant-scoped field-by-field update. Returns None on cross-tenant miss."""
        page = await self.get(page_id)
        if page is None or page.tenant_id != tenant_id:
            return None
        for field_name in ("title", "slug", "body", "source_url", "status"):
            if field_name in body:
                setattr(page, field_name, body[field_name])
        await self._session.flush()
        return page

    async def set_status(
        self, page_id: UUID, tenant_id: UUID, status: str
    ) -> CmsPage | None:
        page = await self.get(page_id)
        if page is None or page.tenant_id != tenant_id:
            return None
        page.status = status
        await self._session.flush()
        return page

    async def soft_delete(self, page_id: UUID, tenant_id: UUID) -> bool:
        """Mark archived (and keep the row for audit-trail) rather than DELETE."""
        page = await self.get(page_id)
        if page is None or page.tenant_id != tenant_id:
            return False
        page.status = "archived"
        await self._session.flush()
        return True
