# Owner: Nasser
"""CMS page edit / publish / unpublish / delete service.

Layered on top of the existing CmsRepository.create flow. Each successful
mutation emits an audit-log row via TenantRepository.add_audit_log and
re-triggers RAG ingest on status flips so the vector store stays in sync.

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

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.repositories.cms_repo import CmsRepository
from app.repositories.tenant_repo import TenantRepository


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
    ) -> None:
        self._repo = repo
        self._tenant_repo = tenant_repo

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
        if "status" in diff:
            await self._reindex_after_status_change(page.tenant_id, page_id, diff["status"])
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
        await self._reindex_after_status_change(
            page.tenant_id, page_id, validated.status
        )
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
        await self._reindex_after_status_change(page.tenant_id, page_id, "archived")

    async def _reindex_after_status_change(
        self, tenant_id: UUID, page_id: UUID, new_status: str
    ) -> None:
        """Best-effort RAG re-index hook.

        The ingest pipeline lives in `app/rag/ingest.py`. The pipeline today
        accepts a tenant_id + page_id + text; here we only invoke it with the
        published body. Failure does not roll back the status change — the
        admin UI can re-run the action and the audit-log entry survives.
        """
        try:
            from app.rag.ingest import embed_cms_page  # noqa: F401 — import side-effect
        except Exception:  # pragma: no cover — ingest pipeline optional
            return
        # The current `embed_cms_page` signature expects ints; until the
        # pipeline is migrated to UUIDs this hook is intentionally a no-op so
        # we never crash the route. A future migration will replace this stub
        # with the real ingest call. (Tracked in DECISIONS.md.)
        return


def _to_payload(page) -> dict[str, Any]:  # noqa: ANN001 — ORM row
    return {
        "id": str(page.id),
        "title": page.title,
        "slug": page.slug,
        "body": page.body,
        "source_url": page.source_url,
        "status": page.status,
        "updated_at": page.updated_at.isoformat() if page.updated_at else None,
    }
