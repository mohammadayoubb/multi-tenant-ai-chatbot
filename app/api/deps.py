# Owner: Hiba
"""FastAPI dependencies.

This file resolves request-scoped dependencies such as tenant context and DB session.
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID
import os

from fastapi import Header, HTTPException, Depends

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_session
from app.domain.tenant import PlatformRole
from app.repositories.tenant_repo import TenantRepository
from app.services.tenant_service import TenantService


@dataclass(frozen=True)
class PlatformActor:
    """Trusted platform actor context resolved by server-side auth."""

    actor_id: str
    actor_role: PlatformRole


async def get_tenant_id_from_widget_token(
    authorization: Annotated[str | None, Header()] = None,
) -> UUID:
    """Resolve tenant_id from a signed widget token.

    Amer owns the final widget token flow. Until that verifier lands, this
    dependency refuses requests instead of returning an unsafe placeholder tenant.
    """
    if authorization is None:
        raise HTTPException(status_code=401, detail="Missing widget token")
    raise HTTPException(status_code=501, detail="Widget token verification is not implemented")


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
    return 1


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
