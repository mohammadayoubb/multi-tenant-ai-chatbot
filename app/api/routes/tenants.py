# Owner: Hiba
"""Tenant management routes."""

from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from app.api.deps import PlatformActor, get_platform_actor, get_tenant_service
from app.domain.tenant import PlatformRole, UsageEvent
from app.schemas.tenant import (
    EraseTenantRequest,
    ErasureResponse,
    RateLimitResponse,
    SuspendTenantRequest,
    TenantCreateRequest,
    TenantResponse,
    UsageEventRequest,
)
from app.services.tenant_service import TenantNotFoundError, TenantPermissionError, TenantService

router = APIRouter(prefix="/tenants", tags=["tenants"])


@router.post("", response_model=TenantResponse, status_code=status.HTTP_201_CREATED)
async def create_tenant(
    request: TenantCreateRequest,
    actor: Annotated[PlatformActor, Depends(get_platform_actor)],
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> TenantResponse:
    """Provision a tenant."""
    try:
        tenant = await service.provision_tenant(
            name=request.name,
            actor_role=actor.actor_role,
            actor_id=actor.actor_id,
        )
    except TenantPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    return TenantResponse.model_validate(tenant)


@router.get("/{tenant_id}", response_model=TenantResponse)
async def get_tenant(
    tenant_id: UUID,
    actor: Annotated[PlatformActor, Depends(get_platform_actor)],
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> TenantResponse:
    """Return tenant metadata only."""
    try:
        tenant = await service.get_tenant(tenant_id, actor_role=actor.actor_role)
    except TenantPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TenantResponse.model_validate(tenant)


@router.post("/{tenant_id}/suspend", response_model=TenantResponse)
async def suspend_tenant(
    tenant_id: UUID,
    request: SuspendTenantRequest,
    actor: Annotated[PlatformActor, Depends(get_platform_actor)],
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> TenantResponse:
    """Suspend a tenant."""
    try:
        tenant = await service.suspend_tenant(
            tenant_id=tenant_id,
            actor_role=actor.actor_role,
            actor_id=actor.actor_id,
            reason=request.reason,
        )
    except TenantPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return TenantResponse.model_validate(tenant)


@router.delete("/{tenant_id}", response_model=ErasureResponse)
async def erase_tenant(
    tenant_id: UUID,
    request: EraseTenantRequest,
    actor: Annotated[PlatformActor, Depends(get_platform_actor)],
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> ErasureResponse:
    """Erase a tenant and tenant-owned rows."""
    try:
        result = await service.erase_tenant(
            tenant_id=tenant_id,
            actor_role=actor.actor_role,
            actor_id=actor.actor_id,
            reason=request.reason,
        )
    except TenantPermissionError as exc:
        raise HTTPException(status_code=403, detail=str(exc)) from exc
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return ErasureResponse.model_validate(result)


@router.post("/{tenant_id}/usage", status_code=status.HTTP_204_NO_CONTENT)
async def record_usage(
    tenant_id: UUID,
    request: UsageEventRequest,
    actor: Annotated[PlatformActor, Depends(get_platform_actor)],
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> Response:
    """Record tenant-scoped usage."""
    _require_platform_accounting_actor(actor)
    try:
        await service.record_usage(
            tenant_id,
            UsageEvent(
                feature=request.feature,
                units=request.units,
                unit_type=request.unit_type,
                estimated_cost_usd=request.estimated_cost_usd,
                trace_id=request.trace_id,
            ),
        )
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{tenant_id}/rate-limit/{action}", response_model=RateLimitResponse)
async def check_rate_limit(
    tenant_id: UUID,
    action: str,
    actor: Annotated[PlatformActor, Depends(get_platform_actor)],
    service: Annotated[TenantService, Depends(get_tenant_service)],
) -> RateLimitResponse:
    """Check one tenant action against its configured rate limit."""
    _require_platform_accounting_actor(actor)
    try:
        result = await service.check_rate_limit(tenant_id, action)
    except TenantNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return RateLimitResponse.model_validate(result)


def _require_platform_accounting_actor(actor: PlatformActor) -> None:
    """Allow platform managers and tenant admins to inspect accounting state."""
    if actor.actor_role not in {PlatformRole.TENANT_MANAGER, PlatformRole.TENANT_ADMIN}:
        raise HTTPException(status_code=403, detail="Actor cannot access tenant accounting")
