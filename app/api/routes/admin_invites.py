# Owner: Amer
"""Admin invite routes.

- `POST /admin/invites` — gated by `require_tenant_admin`. The inviter's
  tenant_id and actor_id come from THEIR JWT (the `TenantAdminContext`); the
  request body cannot override either.
- `GET /admin/invites/{token}` — public; returns safe metadata only so the
  accept-invite page can render the email + tenant name + status banner.
- `POST /admin/invites/{token}/accept` — public; creates the admin_user row
  using tenant_id / role / email pulled from the invite, never from the body.
"""

from __future__ import annotations

import json
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantAdminContext, require_admin_session
from app.db.session import get_session
from app.domain.admin_invite import (
    InviteAcceptRequest,
    InviteCreateRequest,
)
from app.repositories.admin_invite_repo import AdminInviteRepository
from app.repositories.admin_user_repo import AdminUserRepository
from app.repositories.tenant_repo import TenantRepository
from app.services.admin_invite import (
    InviteUnavailable,
    WeakPassword,
    accept_invite,
    create_invite,
    get_invite_details,
)

router = APIRouter(prefix="/admin/invites", tags=["admin-invites"])

_HEADERS = {"Cache-Control": "no-store", "Content-Type": "application/json"}
_FORBIDDEN_BODY = b'{"error":"forbidden"}'
_BAD_REQUEST_BODY = b'{"error":"bad_request"}'
_INVITE_UNAVAILABLE_BODY = b'{"error":"invite_unavailable"}'


def _bytes_response(status: int, body: bytes) -> Response:
    return Response(status_code=status, content=body, headers=_HEADERS)


def _json_response(status: int, payload: dict) -> Response:
    return Response(
        status_code=status,
        content=json.dumps(payload, separators=(",", ":"), default=str).encode(
            "utf-8"
        ),
        headers=_HEADERS,
    )


# ---------------------------------------------------------------------------
# Create — gated
# ---------------------------------------------------------------------------


@router.post("")
async def create(
    request: Request,
    admin: TenantAdminContext | None = Depends(require_admin_session),
    session: AsyncSession = Depends(get_session),
) -> Response:
    if admin is None:
        return _bytes_response(403, _FORBIDDEN_BODY)
    try:
        raw = await request.json()
    except json.JSONDecodeError:
        return _bytes_response(400, _BAD_REQUEST_BODY)
    try:
        body = InviteCreateRequest.model_validate(raw)
    except ValidationError:
        return _bytes_response(400, _BAD_REQUEST_BODY)

    response = await create_invite(
        request=body,
        inviter_tenant_id=admin.tenant_id,
        inviter_actor_id=admin.actor_id or "unknown",
        repo=AdminInviteRepository(session),
    )
    return _json_response(200, response.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Details — public, safe metadata
# ---------------------------------------------------------------------------


@router.get("/{token}")
async def details(
    token: UUID,
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        response = await get_invite_details(
            token=token,
            invite_repo=AdminInviteRepository(session),
            tenant_repo=TenantRepository(session),
        )
    except InviteUnavailable:
        return _bytes_response(404, _INVITE_UNAVAILABLE_BODY)
    return _json_response(200, response.model_dump(mode="json"))


# ---------------------------------------------------------------------------
# Accept — public, creates admin_user from invite fields
# ---------------------------------------------------------------------------


@router.post("/{token}/accept")
async def accept(
    token: UUID,
    request: Request,
    session: AsyncSession = Depends(get_session),
) -> Response:
    try:
        raw = await request.json()
    except json.JSONDecodeError:
        return _bytes_response(400, _BAD_REQUEST_BODY)
    try:
        body = InviteAcceptRequest.model_validate(raw)
    except ValidationError:
        return _bytes_response(400, _BAD_REQUEST_BODY)

    try:
        user = await accept_invite(
            token=token,
            request=body,
            invite_repo=AdminInviteRepository(session),
            user_repo=AdminUserRepository(session),
        )
    except WeakPassword as exc:
        return _json_response(
            422,
            {"error": "weak_password", "message": str(exc)},
        )
    except InviteUnavailable:
        return _bytes_response(400, _INVITE_UNAVAILABLE_BODY)

    return _json_response(
        200,
        {
            "id": str(user.id),
            "email": user.email,
            "tenant_id": str(user.tenant_id),
            "role": user.role,
        },
    )
