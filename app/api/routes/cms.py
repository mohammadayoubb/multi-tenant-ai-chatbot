# Owner: Hiba (admin endpoints contributed by Amer for BLOCKED.md N1/N9)
"""CMS routes for tenant admins.

GET /cms/pages   — list the caller's tenant CMS pages
POST /cms/pages  — create a CMS page in the caller's tenant

`tenant_id` ALWAYS comes from the admin JWT (`require_admin_session`).
There is no `tenant_id` field on the create request — even if the body
includes one, it is ignored.
"""

from __future__ import annotations

from typing import Annotated
from uuid import UUID

import json

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantAdminContext, require_admin_session, require_tenant_admin
from app.db.session import get_session
from app.repositories.cms_repo import CmsRepository
from app.repositories.tenant_repo import TenantRepository
from app.services.cms_pages import (
    CmsActor,
    CmsPageInvalid,
    CmsPageNotFound,
    CmsPageService,
)

router = APIRouter(prefix="/cms", tags=["cms"])


def _require_admin(admin: TenantAdminContext | None) -> TenantAdminContext:
    if admin is None:
        raise HTTPException(status_code=403, detail="forbidden")
    return admin


def _refuse_tenant_manager(admin: TenantAdminContext) -> TenantAdminContext:
    """FR-046: tenant_manager must not see tenant CMS content."""
    if admin.role == "tenant_manager":
        raise HTTPException(status_code=403, detail="forbidden")
    return admin


class CmsPageResponse(BaseModel):
    """Shape consumed by admin/cms_page.py."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    title: str
    slug: str
    body: str
    source_url: str | None
    status: str
    updated_at: str

    @classmethod
    def from_row(cls, row) -> "CmsPageResponse":  # type: ignore[no-untyped-def]
        return cls(
            id=row.id,
            title=row.title,
            slug=row.slug,
            body=row.body,
            source_url=row.source_url,
            status=row.status,
            updated_at=row.updated_at.isoformat() if row.updated_at else "",
        )


class CmsPageCreateRequest(BaseModel):
    """Create-page body. `tenant_id` is intentionally absent (CONTRACT.md §7)."""

    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    source_url: str | None = None
    status: str = Field(default="published", pattern="^(draft|published|archived)$")


@router.get("/pages", response_model=list[CmsPageResponse])
async def list_pages(
    admin: Annotated[TenantAdminContext | None, Depends(require_admin_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[CmsPageResponse]:
    """List CMS pages for the caller's tenant only."""
    ctx = _refuse_tenant_manager(_require_admin(admin))
    repo = CmsRepository(session)
    rows = await repo.list_pages(ctx.tenant_id)
    return [CmsPageResponse.from_row(r) for r in rows]


@router.post("/pages", response_model=CmsPageResponse, status_code=status.HTTP_201_CREATED)
async def create_page(
    request: CmsPageCreateRequest,
    admin: Annotated[TenantAdminContext | None, Depends(require_admin_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> CmsPageResponse:
    """Create one CMS page in the caller's tenant (tenant_id from JWT)."""
    ctx = _refuse_tenant_manager(_require_admin(admin))
    repo = CmsRepository(session)
    page = await repo.create(
        tenant_id=ctx.tenant_id,
        title=request.title,
        slug=request.slug,
        body=request.body,
        source_url=request.source_url,
        status=request.status,
        created_by=ctx.actor_id,
    )
    return CmsPageResponse.from_row(page)


def _service(session: AsyncSession) -> CmsPageService:
    return CmsPageService(CmsRepository(session), TenantRepository(session))


def _actor(admin: TenantAdminContext) -> CmsActor:
    return CmsActor(
        tenant_id=admin.tenant_id,
        actor_id=admin.actor_id or "unknown",
        role=admin.role,
    )


@router.put("/pages/{page_id}")
async def update_page(
    page_id: UUID,
    request: Request,
    admin: Annotated[TenantAdminContext | None, Depends(require_tenant_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """Edit a CMS page. tenant_id NEVER read from the body."""
    ctx = _require_admin(admin)
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="bad_request") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="bad_request")
    try:
        return await _service(session).update(page_id, body, _actor(ctx))
    except CmsPageNotFound as exc:
        raise HTTPException(status_code=403, detail="forbidden") from exc
    except CmsPageInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.patch("/pages/{page_id}/status")
async def patch_page_status(
    page_id: UUID,
    request: Request,
    admin: Annotated[TenantAdminContext | None, Depends(require_tenant_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    ctx = _require_admin(admin)
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="bad_request") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="bad_request")
    try:
        return await _service(session).set_status(page_id, body, _actor(ctx))
    except CmsPageNotFound as exc:
        raise HTTPException(status_code=403, detail="forbidden") from exc
    except CmsPageInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.delete("/pages/{page_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_page(
    page_id: UUID,
    admin: Annotated[TenantAdminContext | None, Depends(require_tenant_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> Response:
    ctx = _require_admin(admin)
    try:
        await _service(session).delete(page_id, _actor(ctx))
    except CmsPageNotFound as exc:
        raise HTTPException(status_code=403, detail="forbidden") from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
