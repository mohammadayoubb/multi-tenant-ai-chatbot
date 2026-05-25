# Owner: Hiba
"""CMS service.

The same CMS content powers the public site and the agent knowledge base.
"""

from app.domain.cms import CmsPageDomain
from app.repositories.cms_repo import CmsRepository


class CmsService:
    """CMS business logic."""

    def __init__(self, repo: CmsRepository) -> None:
        self._repo = repo

    async def list_pages(self, tenant_id: int) -> list[CmsPageDomain]:
        """List tenant CMS pages."""
        pages = await self._repo.list_pages(tenant_id)
        return [CmsPageDomain.model_validate(page) for page in pages]
