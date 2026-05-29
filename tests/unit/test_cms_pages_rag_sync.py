from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.rag import ingest
from app.services.cms_pages import CmsActor, CmsPageService


@dataclass
class _Page:
    id: UUID
    tenant_id: UUID
    title: str
    slug: str
    body: str
    source_url: str | None
    status: str
    created_by: str | None = None
    updated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


class _Repo:
    def __init__(self) -> None:
        self.pages: dict[UUID, _Page] = {}

    async def create(self, **kwargs) -> _Page:
        page = _Page(id=uuid4(), **kwargs)
        self.pages[page.id] = page
        return page

    async def update(self, page_id: UUID, tenant_id: UUID, body: dict) -> _Page | None:
        page = self.pages.get(page_id)
        if page is None or page.tenant_id != tenant_id:
            return None
        for key, value in body.items():
            setattr(page, key, value)
        return page

    async def set_status(
        self,
        page_id: UUID,
        tenant_id: UUID,
        status: str,
    ) -> _Page | None:
        return await self.update(page_id, tenant_id, {"status": status})

    async def get(self, page_id: UUID) -> _Page | None:
        return self.pages.get(page_id)

    async def soft_delete(self, page_id: UUID, tenant_id: UUID) -> bool:
        page = await self.update(page_id, tenant_id, {"status": "archived"})
        return page is not None


class _TenantRepo:
    def __init__(self) -> None:
        self.audit_events: list[dict[str, object]] = []

    async def add_audit_log(self, **kwargs) -> None:
        self.audit_events.append(kwargs)


@pytest.mark.asyncio
async def test_cms_create_syncs_published_page_to_rag(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    async def _sync(_session, **kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(ingest, "sync_cms_page_index", _sync)
    tenant_id = uuid4()
    session = object()
    service = CmsPageService(_Repo(), _TenantRepo(), session)  # type: ignore[arg-type]

    payload = await service.create(
        title="Pricing",
        slug="pricing",
        body="Plans start at 40 dollars.",
        source_url=None,
        status="published",
        actor=CmsActor(tenant_id=tenant_id, actor_id="admin@example.test", role="tenant_admin"),
    )

    assert payload["slug"] == "pricing"
    assert calls[0]["tenant_id"] == tenant_id
    assert calls[0]["page_id"] == UUID(str(payload["id"]))
    assert calls[0]["status"] == "published"
    assert calls[0]["text"] == "Plans start at 40 dollars."


@pytest.mark.asyncio
async def test_cms_update_and_status_change_resync_current_page(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    async def _sync(_session, **kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(ingest, "sync_cms_page_index", _sync)
    tenant_id = uuid4()
    repo = _Repo()
    tenant_repo = _TenantRepo()
    service = CmsPageService(repo, tenant_repo, object())  # type: ignore[arg-type]
    actor = CmsActor(tenant_id=tenant_id, actor_id="admin@example.test", role="tenant_admin")
    page = await repo.create(
        tenant_id=tenant_id,
        title="Hours",
        slug="hours",
        body="Old hours.",
        source_url=None,
        status="published",
        created_by=actor.actor_id,
    )

    await service.update(page.id, {"body": "New hours."}, actor)
    await service.set_status(page.id, {"status": "draft"}, actor)

    assert calls[0]["text"] == "New hours."
    assert calls[0]["status"] == "published"
    assert calls[1]["text"] == "New hours."
    assert calls[1]["status"] == "draft"
    assert [event["action"] for event in tenant_repo.audit_events] == [
        "cms.page_updated",
        "cms.page_unpublished",
    ]


@pytest.mark.asyncio
async def test_cms_delete_removes_page_from_rag(monkeypatch) -> None:
    calls: list[dict[str, object]] = []

    async def _delete(_session, **kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(ingest, "delete_cms_page_chunks", _delete)
    tenant_id = uuid4()
    repo = _Repo()
    service = CmsPageService(repo, _TenantRepo(), object())  # type: ignore[arg-type]
    actor = CmsActor(tenant_id=tenant_id, actor_id="admin@example.test", role="tenant_admin")
    page = await repo.create(
        tenant_id=tenant_id,
        title="Archived",
        slug="archived",
        body="Old content.",
        source_url=None,
        status="published",
        created_by=actor.actor_id,
    )

    await service.delete(page.id, actor)

    assert calls == [{"tenant_id": tenant_id, "page_id": page.id}]
    assert repo.pages[page.id].status == "archived"
