# Owner: Amer (BLOCKED.md N8 — admin reads tenant leads)
"""GET /leads — list the caller's tenant leads.

Used by admin/leads_page.py. The admin Streamlit page redacts the `contact`
field before display (FR-009); the API returns the unredacted value so other
admin tooling (export, CRM sync) can use it. Auth is the admin JWT — there
is no path tenant_id; the JWT's `tenant_id` is the only thing that scopes
the query.
"""

from __future__ import annotations

from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantAdminContext, require_admin_session
from app.db.session import get_session
from app.repositories.lead_repo import LeadRepository

router = APIRouter(prefix="/leads", tags=["leads"])


class LeadResponse(BaseModel):
    id: UUID
    created_at: datetime
    name: str | None
    contact: str | None
    intent: str
    status: str
    quality_score: float | None


@router.get("", response_model=list[LeadResponse])
async def list_leads(
    admin: Annotated[TenantAdminContext | None, Depends(require_admin_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    limit: int = 100,
) -> list[LeadResponse]:
    """Return up to `limit` leads for the caller's tenant, newest first."""
    if admin is None:
        raise HTTPException(status_code=403, detail="forbidden")
    if admin.role == "tenant_manager":
        raise HTTPException(status_code=403, detail="forbidden")
    safe_limit = max(1, min(limit, 500))
    repo = LeadRepository(session)
    rows = await repo.list_by_tenant(admin.tenant_id, limit=safe_limit)
    return [
        LeadResponse(
            id=r.id,
            created_at=r.created_at,
            name=r.name,
            contact=r.contact,
            intent=r.intent,
            status=r.status,
            quality_score=r.quality_score,
        )
        for r in rows
    ]
