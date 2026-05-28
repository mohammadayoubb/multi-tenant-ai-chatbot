# Owner: Hiba
"""FastAPI dependencies.

This file resolves request-scoped dependencies such as tenant context and DB session.
"""

from dataclasses import dataclass
from typing import Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException
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
