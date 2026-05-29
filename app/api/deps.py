# Owner: Hiba
"""FastAPI dependencies.

This file resolves request-scoped dependencies such as tenant context and DB session.
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID
import os

import jwt
from fastapi import Header, HTTPException, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.domain.tenant import PlatformRole
from app.repositories.tenant_repo import TenantRepository
from app.services.tenant_service import TenantService
from app.services.widget_settings import widget_settings


@dataclass(frozen=True)
class PlatformActor:
    """Trusted platform actor context resolved by server-side auth."""

    actor_id: str
    actor_role: PlatformRole


async def get_tenant_id_from_widget_token(
    authorization: Annotated[str | None, Header()] = None,
) -> UUID:
    """Resolve tenant_id from a signed widget token.

    Verifies the HS256 JWT minted by `WidgetTokenService._mint_jwt`
    (see specs/001-widget-token-exchange/contracts/widget-token-endpoint.md
    "Out of scope" — this dep is the authoritative consumer of WIDGET_JWT_SECRET).
    Any decode/signature/expiry failure collapses to a single 401 so callers
    cannot distinguish "no token" from "bad token" from "expired token".
    """
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing widget token")
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid widget token")
    try:
        payload = jwt.decode(
            token,
            widget_settings().widget_jwt_secret,
            algorithms=["HS256"],
        )
    except jwt.PyJWTError:
        raise HTTPException(status_code=401, detail="Invalid widget token")
    raw_tenant_id = payload.get("tenant_id")
    if not isinstance(raw_tenant_id, str):
        raise HTTPException(status_code=401, detail="Invalid widget token")
    try:
        return UUID(raw_tenant_id)
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid widget token")


async def get_platform_actor(
    actor_id: Annotated[str | None, Header(alias="X-Actor-ID")] = None,
    actor_role: Annotated[str | None, Header(alias="X-Actor-Role")] = None,
) -> PlatformActor:
    """Resolve platform actor context from trusted upstream auth headers."""
    if actor_id is None or actor_role is None:
        raise HTTPException(status_code=401, detail="Missing platform actor context")
    try:
        role = PlatformRole(actor_role)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Unsupported platform actor role") from exc
    return PlatformActor(actor_id=actor_id, actor_role=role)


async def get_tenant_repository(
    session: Annotated[AsyncSession, Depends(get_session)],
) -> TenantRepository:
    """Build a request-scoped tenant repository."""
    return TenantRepository(session)


async def get_tenant_service(
    repo: Annotated[TenantRepository, Depends(get_tenant_repository)],
) -> TenantService:
    """Build a request-scoped tenant service."""
    return TenantService(repo)


@dataclass(frozen=True)
class TenantAdminContext:
    """Trusted context returned by require_tenant_admin.

    Shape contract: tenant_id is the caller's tenant; actor_id is the admin
    user id (or None until the real session model lands). `role` is one of
    `tenant_admin` / `tenant_manager` (filtered by the calling dep); routes
    that need to gate by role read it from here instead of redecoding the JWT.
    """

    tenant_id: UUID
    actor_id: str | None
    role: str = "tenant_admin"


async def require_admin_session(
    authorization: Annotated[str | None, Header()] = None,
    x_concierge_role: str | None = Header(default=None, alias="X-Concierge-Role"),
    x_concierge_tenant_id: str | None = Header(
        default=None, alias="X-Concierge-Tenant-Id"
    ),
    x_concierge_actor_id: str | None = Header(
        default=None, alias="X-Concierge-Actor-Id"
    ),
) -> TenantAdminContext | None:
    """Accept any logged-in admin role (`tenant_admin` OR `tenant_manager`).

    Used by routes (e.g. POST /admin/invites) where both roles legitimately
    act on behalf of their own tenant. Returns the same TenantAdminContext
    shape as `require_tenant_admin`; the `role` claim is preserved in the JWT
    even though it's not part of the returned dataclass.
    """
    from app.services.admin_auth import verify_admin_token

    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            session = verify_admin_token(token)
            if session is not None and session.role in (
                "tenant_admin",
                "tenant_manager",
            ):
                return TenantAdminContext(
                    tenant_id=session.tenant_id,
                    actor_id=session.actor_id,
                    role=session.role,
                )

    if os.getenv("CONCIERGE_ENV", "dev") != "dev":
        return None
    if x_concierge_role not in ("tenant_admin", "tenant_manager"):
        return None
    if not x_concierge_tenant_id:
        return None
    try:
        tenant_id = UUID(x_concierge_tenant_id)
    except ValueError:
        return None
    return TenantAdminContext(
        tenant_id=tenant_id,
        actor_id=x_concierge_actor_id,
        role=x_concierge_role,
    )


async def require_tenant_admin(
    authorization: Annotated[str | None, Header()] = None,
    x_concierge_role: str | None = Header(default=None, alias="X-Concierge-Role"),
    x_concierge_tenant_id: str | None = Header(
        default=None, alias="X-Concierge-Tenant-Id"
    ),
    x_concierge_actor_id: str | None = Header(
        default=None, alias="X-Concierge-Actor-Id"
    ),
) -> TenantAdminContext | None:
    """Tenant-admin gate.

    Resolution order:
      1. Real admin JWT in `Authorization: Bearer <token>` (production path).
      2. Dev headers `X-Concierge-Role` / `X-Concierge-Tenant-Id` /
         `X-Concierge-Actor-Id` — ONLY honored when CONCIERGE_ENV=dev. Used by
         the existing widget-admin test suite; not reachable in staging/prod.

    Returns `TenantAdminContext` on success; returns `None` when the request
    fails every path — the calling route produces a byte-identical 403 for
    every refusal cause (contract clauses E1/E3 in feature 004).
    """
    # Local import to avoid an import cycle between deps and the admin service.
    from app.services.admin_auth import verify_admin_token

    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            session = verify_admin_token(token)
            if session is not None and session.role == "tenant_admin":
                return TenantAdminContext(
                    tenant_id=session.tenant_id,
                    actor_id=session.actor_id,
                    role=session.role,
                )

    if os.getenv("CONCIERGE_ENV", "dev") != "dev":
        return None
    if x_concierge_role != "tenant_admin":
        return None
    if not x_concierge_tenant_id:
        return None
    try:
        tenant_id = UUID(x_concierge_tenant_id)
    except ValueError:
        return None
    return TenantAdminContext(
        tenant_id=tenant_id,
        actor_id=x_concierge_actor_id,
        role="tenant_admin",
    )
