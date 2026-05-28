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
from jwt import ExpiredSignatureError, InvalidTokenError

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.domain.tenant import PlatformRole
from app.repositories.tenant_repo import TenantRepository
from app.repositories.widget_repo import get_widget_repository
from app.services.admin_auth import AdminTokenError, AdminAuthService, get_admin_account_repository
from app.services.widget_service import normalize_origin
from app.services.widget_settings import widget_settings
from app.services.tenant_service import TenantService


@dataclass(frozen=True)
class PlatformActor:
    """Trusted platform actor context resolved by server-side auth."""

    actor_id: str
    actor_role: PlatformRole


async def get_tenant_id_from_widget_token(
    authorization: Annotated[str | None, Header()] = None,
    origin: Annotated[str | None, Header()] = None,
) -> UUID:
    """Resolve tenant_id from a signed widget token.

    The widget token is the only trusted tenant identity input for public chat.
    The dependency verifies the JWT, checks the claimed origin against the
    browser-supplied request Origin header, then confirms the widget row still
    belongs to the claimed tenant and allowlists that origin.
    """
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing widget token")

    scheme, _, raw_token = authorization.partition(" ")
    token = raw_token.strip()
    if scheme.lower() != "bearer" or not token:
        raise HTTPException(status_code=401, detail="Invalid widget token")

    try:
        claims = jwt.decode(
            token,
            widget_settings().widget_jwt_secret,
            algorithms=["HS256"],
            options={
                "require": ["tenant_id", "widget_id", "origin", "session_id", "iat", "exp"]
            },
        )
    except ExpiredSignatureError as exc:
        raise HTTPException(status_code=401, detail="Widget token expired") from exc
    except InvalidTokenError as exc:
        raise HTTPException(status_code=401, detail="Invalid widget token") from exc

    try:
        tenant_id = UUID(str(claims["tenant_id"]))
        widget_id = UUID(str(claims["widget_id"]))
        token_origin = normalize_origin(str(claims["origin"]))
        UUID(str(claims["session_id"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=401, detail="Invalid widget token") from exc

    if origin is None:
        raise HTTPException(status_code=403, detail="Widget origin mismatch")

    try:
        request_origin = normalize_origin(origin)
    except ValueError as exc:
        raise HTTPException(status_code=403, detail="Widget origin mismatch") from exc

    if request_origin != token_origin:
        raise HTTPException(status_code=403, detail="Widget origin mismatch")

    repo = get_widget_repository()
    config = await repo.get_by_widget_id(widget_id)
    if config is None:
        raise HTTPException(status_code=403, detail="Widget origin mismatch")

    allowed_origins = {normalize_origin(value) for value in config.allowed_origins}
    if config.tenant_id != tenant_id or token_origin not in allowed_origins:
        raise HTTPException(status_code=403, detail="Widget origin mismatch")

    return tenant_id


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
    user id (or None until the real session model lands). The role check is
    already enforced by the time this object is constructed.
    """

    tenant_id: UUID
    actor_id: str | None


# TODO(hiba-handoff): replace with Hiba's authenticated role dep when it lands.
# Edit authorized for feature 004; see specs/004-widget-admin-config/plan.md
# Complexity Tracking. Until then, the mock reads dev headers and refuses to
# operate outside CONCIERGE_ENV=dev so it cannot ship to staging/prod.
#
# Returns Optional[TenantAdminContext] (not raise-on-refused) so the calling
# route can produce a byte-identical 403 body for every refusal path (contract
# E1/E3 indistinguishability — same bytes whether the role is missing, the
# tenant id is missing, or the row doesn't exist).
async def require_tenant_admin(
    authorization: str | None = Header(default=None, alias="Authorization"),
    x_concierge_role: str | None = Header(default=None, alias="X-Concierge-Role"),
    x_concierge_tenant_id: str | None = Header(
        default=None, alias="X-Concierge-Tenant-Id"
    ),
    x_concierge_actor_id: str | None = Header(
        default=None, alias="X-Concierge-Actor-Id"
    ),
) -> TenantAdminContext | None:
    """Mock tenant_admin gate.

    Returns a TenantAdminContext when the request carries valid admin headers.
    Returns None when the headers are missing, wrong, or malformed — the route
    handler converts this to the canonical 403 byte response.

    Raises HTTPException(500) outside CONCIERGE_ENV=dev to prevent accidental
    promotion of header-driven auth.
    """
    if authorization is not None:
        scheme, _, raw_token = authorization.partition(" ")
        token = raw_token.strip()
        if scheme.lower() == "bearer" and token:
            auth_service = AdminAuthService(
                accounts=get_admin_account_repository(),
                widget_repo=get_widget_repository(),
            )
            try:
                session = auth_service.verify_token(token)
            except AdminTokenError:
                session = None
            if session is not None:
                return TenantAdminContext(
                    tenant_id=session.tenant_id,
                    actor_id=session.actor_id,
                )

    if os.getenv("CONCIERGE_ENV", "dev") != "dev":
        raise HTTPException(
            status_code=500,
            detail="role-dep mock disabled in non-dev environments",
        )
    if x_concierge_role != "tenant_admin":
        return None
    if not x_concierge_tenant_id:
        return None
    try:
        tenant_id = UUID(x_concierge_tenant_id)
    except ValueError:
        return None
    return TenantAdminContext(tenant_id=tenant_id, actor_id=x_concierge_actor_id)
