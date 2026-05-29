# Owner: Nasser
"""Escalation list + patch routes.

GET /escalations?tenant_id={tid}  — admin-JWT-gated; tenant_id MUST equal
                                     the JWT's tenant_id (TA scope). TM may
                                     pass any tid.
PATCH /escalations/{id}            — admin-JWT-gated; ticket MUST belong to
                                     the JWT tenant.
"""

from __future__ import annotations

import json
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantAdminContext, require_admin_session
from app.db.session import get_session
from app.repositories.admin_user_repo import AdminUserRepository
from app.repositories.escalation_repo import EscalationRepository
from app.repositories.tenant_repo import TenantRepository
from app.services.escalation import (
    EscalationActor,
    EscalationForbidden,
    EscalationInvalid,
    EscalationNotFound,
    EscalationService,
)

router = APIRouter(prefix="/escalations", tags=["escalations"])


def _service(session: AsyncSession) -> EscalationService:
    return EscalationService(
        EscalationRepository(session),
        AdminUserRepository(session),
        TenantRepository(session),
    )


@router.get("")
async def list_escalations(
    admin: Annotated[TenantAdminContext | None, Depends(require_admin_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    tenant_id: UUID | None = None,
) -> list[dict]:
    if admin is None:
        raise HTTPException(status_code=403, detail="forbidden")
    # FR-046: tenant_manager must not see tenant content (tickets include
    # message excerpts). TA-only.
    if admin.role == "tenant_manager":
        raise HTTPException(status_code=403, detail="forbidden")
    target = tenant_id or admin.tenant_id
    if target != admin.tenant_id:
        raise HTTPException(status_code=403, detail="forbidden")
    return await _service(session).list_for_tenant(target)


@router.patch("/{ticket_id}")
async def patch_escalation(
    ticket_id: UUID,
    request: Request,
    admin: Annotated[TenantAdminContext | None, Depends(require_admin_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    if admin is None:
        raise HTTPException(status_code=403, detail="forbidden")
    if admin.role == "tenant_manager":
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        body = await request.json()
    except json.JSONDecodeError as exc:
        raise HTTPException(status_code=400, detail="bad_request") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="bad_request")

    service = _service(session)
    try:
        return await service.patch(
            ticket_id,
            body,
            EscalationActor(
                tenant_id=admin.tenant_id,
                actor_id=admin.actor_id or "unknown",
                role=admin.role,
            ),
        )
    except EscalationNotFound as exc:
        raise HTTPException(status_code=404, detail="not_found") from exc
    except EscalationForbidden as exc:
        raise HTTPException(status_code=403, detail="forbidden") from exc
    except EscalationInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
