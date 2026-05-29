# Owner: Nasser
"""CMS page create / edit / publish / unpublish / delete service.

Each successful mutation keeps the tenant RAG index in sync. Edit / status /
delete operations also emit audit rows via TenantRepository.add_audit_log.

Audit events:
- cms.page_updated
- cms.page_published
- cms.page_unpublished
- cms.page_deleted

Validation policy:
- Tenant_id is NEVER read from the request body — the route is responsible
  for handing the trusted JWT-derived tenant_id to this service.
- `extra=forbid` on the body schemas guarantees `tenant_id` smuggled in
  the body fails with 422 at the route boundary.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.repositories.cms_repo import CmsRepository
from app.repositories.tenant_repo import TenantRepository

LOGGER = logging.getLogger(__name__)

_ALLOWED_STATUSES = ("draft", "published", "archived")


class CmsPageNotFound(Exception):
    """Page id does not exist OR does not belong to the caller's tenant."""


class CmsPageInvalid(Exception):
    """Body failed validation."""


@dataclass(frozen=True)
class CmsActor:
    tenant_id: UUID
    actor_id: str
    role: str


class CmsPageUpdateBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str | None = Field(default=None, min_length=1, max_length=255)
    slug: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = Field(default=None, min_length=1)
    source_url: str | None = None
    status: str | None = Field(default=None, pattern="^(draft|published|archived)$")


class CmsPageStatusBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str = Field(pattern="^(draft|published|archived)$")


class CmsPageService:
    def __init__(
        self,
        repo: CmsRepository,
        tenant_repo: TenantRepository,
        session: AsyncSession | None = None,
    ) -> None:
        self._repo = repo
        self._tenant_repo = tenant_repo
        self._session = session

    async def create(
        self,
        *,
        title: str,
        slug: str,
        body: str,
        source_url: str | None,
        status: str,
        actor: CmsActor,
    ) -> dict[str, Any]:
        page = await self._repo.create(
            tenant_id=actor.tenant_id,
            title=title,
            slug=slug,
            body=body,
            source_url=source_url,
            status=status,
            created_by=actor.actor_id,
        )
        await self._sync_page_index(page)
        return _to_payload(page)

    async def update(
        self,
        page_id: UUID,
        body: dict[str, Any],
        actor: CmsActor,
    ) -> dict[str, Any]:
        try:
            validated = CmsPageUpdateBody.model_validate(body)
        except ValidationError as exc:
            raise CmsPageInvalid(str(exc)) from exc
        diff = validated.model_dump(exclude_none=True)
        page = await self._repo.update(page_id, actor.tenant_id, diff)
        if page is None:
            raise CmsPageNotFound("unknown")
        await self._tenant_repo.add_audit_log(
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            actor_role=actor.role,
            action="cms.page_updated",
            metadata={"page_id": str(page_id), "fields": sorted(diff.keys())},
        )
        await self._sync_page_index(page)
        return _to_payload(page)

    async def set_status(
        self,
        page_id: UUID,
        body: dict[str, Any],
        actor: CmsActor,
    ) -> dict[str, Any]:
        try:
            validated = CmsPageStatusBody.model_validate(body)
        except ValidationError as exc:
            raise CmsPageInvalid(str(exc)) from exc
        page = await self._repo.set_status(page_id, actor.tenant_id, validated.status)
        if page is None:
            raise CmsPageNotFound("unknown")
        action = (
            "cms.page_published"
            if validated.status == "published"
            else "cms.page_unpublished"
        )
        await self._tenant_repo.add_audit_log(
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            actor_role=actor.role,
            action=action,
            metadata={"page_id": str(page_id), "status": validated.status},
        )
        await self._sync_page_index(page)
        return _to_payload(page)

    async def delete(
        self,
        page_id: UUID,
        actor: CmsActor,
    ) -> None:
        page = await self._repo.get(page_id)
        if page is None or page.tenant_id != actor.tenant_id:
            raise CmsPageNotFound("unknown")
        await self._repo.soft_delete(page_id, actor.tenant_id)
        await self._tenant_repo.add_audit_log(
            tenant_id=actor.tenant_id,
            actor_id=actor.actor_id,
            actor_role=actor.role,
            action="cms.page_deleted",
            metadata={"page_id": str(page_id)},
        )
        await self._delete_page_index(page.tenant_id, page_id)

    async def _sync_page_index(self, page: Any) -> None:
        """Write the page's current state to the RAG index.

        RAG sync is a best-effort side-effect of the CMS mutation: failure
        here must NOT roll back the user's publish/edit/delete. The work is
        wrapped in a SAVEPOINT so a pgvector / RLS / FK error inside the
        ingest call rolls back only the index writes, leaving the outer
        transaction (cms_pages UPDATE + audit_log INSERT) committable.
        """

        if self._session is None:
            return

        from app.rag.ingest import sync_cms_page_index

        try:
            async with self._session.begin_nested():
                await sync_cms_page_index(
                    self._session,
                    tenant_id=page.tenant_id,
                    page_id=page.id,
                    text=page.body,
                    source_title=page.title,
                    source_url=page.source_url,
                    status=page.status,
                )
        except Exception:
            LOGGER.warning(
                "rag_index_sync_failed tenant_id=%s page_id=%s",
                page.tenant_id,
                page.id,
                exc_info=True,
            )

    async def _delete_page_index(self, tenant_id: UUID, page_id: UUID) -> None:
        if self._session is None:
            return

        from app.rag.ingest import delete_cms_page_chunks

        try:
            async with self._session.begin_nested():
                await delete_cms_page_chunks(
                    self._session,
                    tenant_id=tenant_id,
                    page_id=page_id,
                )
        except Exception:
            LOGGER.warning(
                "rag_index_delete_failed tenant_id=%s page_id=%s",
                tenant_id,
                page_id,
                exc_info=True,
            )


def _to_payload(page) -> dict[str, Any]:  # noqa: ANN001 — ORM row
    return {
        "id": str(page.id),
        "title": page.title,
        "slug": page.slug,
        "body": page.body,
        "source_url": page.source_url,
        "status": page.status,
        "updated_at": page.updated_at.isoformat() if page.updated_at else "",
    }
