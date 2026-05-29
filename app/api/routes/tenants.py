# Owner: Hiba
"""Tenant management routes."""

from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException, Request, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import (
    PlatformActor,
    TenantAdminContext,
    get_platform_actor,
    get_tenant_id_from_widget_token,
    get_tenant_repository,
    get_tenant_service,
    require_admin_session,
    require_tenant_admin,
)
from app.db.session import get_session
from app.domain.tenant import AuditLogDomain, PlatformRole, UsageEvent
from app.repositories.tenant_repo import TenantRepository
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
# Platform-scope router exposes paths outside the /tenants prefix (e.g. the
# admin-JWT-gated `/audit-logs` feed consumed by the Tenant Manager dashboard).
# Defined here so all platform reads stay co-located with TenantRepository.
platform_router = APIRouter(tags=["platform"])


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


# ---------------------------------------------------------------------------
# Admin-JWT-authed read endpoints consumed by the Streamlit admin pages.
# These run on the same router but use the admin-session dep (Bearer JWT),
# not the legacy X-Actor-* header dep. The path tenant_id must equal the
# JWT's tenant_id — a tenant_admin cannot read another tenant's audit log.
# ---------------------------------------------------------------------------


def _require_self_tenant(
    path_tenant_id: UUID, admin: TenantAdminContext | None
) -> TenantAdminContext:
    """Refuse missing JWT and cross-tenant reads with one 403 body."""
    if admin is None or admin.tenant_id != path_tenant_id:
        raise HTTPException(status_code=403, detail="forbidden")
    return admin


@router.get("/{tenant_id}/audit-logs")
async def list_tenant_audit_logs(
    tenant_id: UUID,
    admin: Annotated[TenantAdminContext | None, Depends(require_admin_session)],
    repo: Annotated[TenantRepository, Depends(get_tenant_repository)],
) -> list[AuditLogDomain]:
    """Return the most recent audit-log rows for the caller's own tenant."""
    _require_self_tenant(tenant_id, admin)
    rows = await repo.list_audit_logs(tenant_id)
    return [AuditLogDomain.model_validate(r) for r in rows]


@router.get("/{tenant_id}/agent-config")
async def get_agent_config(
    tenant_id: UUID,
    admin: Annotated[TenantAdminContext | None, Depends(require_admin_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
    authorization: Annotated[str | None, Header()] = None,
) -> dict:
    """Read the tenant's agent config.

    Accepts EITHER an admin JWT scoped to this tenant OR a widget JWT scoped
    to this tenant. Cross-tenant reads are refused with one 403 body.
    """
    from app.repositories.agent_config_repo import TenantAgentConfigRepository
    from app.services.agent_config import AgentConfigService

    _ensure_tenant_read_scope(tenant_id, admin, authorization)
    service = AgentConfigService(
        TenantAgentConfigRepository(session), TenantRepository(session)
    )
    return await service.get_for_tenant(tenant_id)


@router.put("/{tenant_id}/agent-config")
async def put_agent_config(
    tenant_id: UUID,
    request: Request,
    admin: Annotated[TenantAdminContext | None, Depends(require_tenant_admin)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """Replace the tenant's agent config (tenant_admin only)."""
    from app.repositories.agent_config_repo import TenantAgentConfigRepository
    from app.services.agent_config import (
        AgentConfigActor,
        AgentConfigInvalid,
        AgentConfigService,
    )

    ctx = _require_self_tenant(tenant_id, admin)
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001 — bad JSON is a 400 below
        raise HTTPException(status_code=400, detail="bad_request") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="bad_request")
    service = AgentConfigService(
        TenantAgentConfigRepository(session), TenantRepository(session)
    )
    try:
        return await service.update_for_tenant(
            tenant_id,
            body,
            AgentConfigActor(
                tenant_id=tenant_id,
                actor_id=ctx.actor_id or "unknown",
                role=ctx.role,
            ),
        )
    except AgentConfigInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/{tenant_id}/admin-users")
async def list_tenant_admin_users(
    tenant_id: UUID,
    admin: Annotated[TenantAdminContext | None, Depends(require_admin_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> list[dict]:
    """List active tenant admin users for the assignee dropdown."""
    from app.repositories.admin_user_repo import AdminUserRepository

    _require_self_tenant(tenant_id, admin)
    rows = await AdminUserRepository(session).list_by_tenant(tenant_id)
    return [
        {
            "actor_id": str(u.id),
            "full_name": u.full_name,
            "email": u.email,
            "role": u.role,
            "status": u.status,
        }
        for u in rows
    ]


@router.get("/{tenant_id}/platform-guardrails")
async def get_platform_guardrails(
    tenant_id: UUID,
    admin: Annotated[TenantAdminContext | None, Depends(require_admin_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """Read-only platform + tenant guardrails snapshot for this tenant."""
    from app.repositories.agent_config_repo import TenantAgentConfigRepository
    from app.services.platform_guardrails import PlatformGuardrailsService

    _require_self_tenant(tenant_id, admin)
    service = PlatformGuardrailsService(TenantAgentConfigRepository(session))
    return await service.snapshot(tenant_id)


@router.put("/{tenant_id}/settings")
async def put_tenant_settings(
    tenant_id: UUID,
    request: Request,
    admin: Annotated[TenantAdminContext | None, Depends(require_admin_session)],
    session: Annotated[AsyncSession, Depends(get_session)],
) -> dict:
    """Update TM-scope tenant settings; tenant_manager role only."""
    from app.repositories.tenant_settings_repo import TenantSettingsRepository
    from app.services.tenant_settings import (
        TenantSettingsActor,
        TenantSettingsForbidden,
        TenantSettingsInvalid,
        TenantSettingsService,
    )

    if admin is None:
        raise HTTPException(status_code=403, detail="forbidden")
    try:
        body = await request.json()
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail="bad_request") from exc
    if not isinstance(body, dict):
        raise HTTPException(status_code=400, detail="bad_request")
    service = TenantSettingsService(
        TenantSettingsRepository(session), TenantRepository(session)
    )
    try:
        return await service.update_for_tenant(
            tenant_id,
            body,
            TenantSettingsActor(
                tenant_id=admin.tenant_id,
                actor_id=admin.actor_id or "unknown",
                role=admin.role,
            ),
        )
    except TenantSettingsForbidden as exc:
        raise HTTPException(status_code=403, detail="forbidden") from exc
    except TenantSettingsInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ---------------------------------------------------------------------------
# TM-scope platform reads (T039u, T039v)
# ---------------------------------------------------------------------------


@router.get("")
async def list_tenants_admin_jwt(
    admin: Annotated[TenantAdminContext | None, Depends(require_admin_session)],
    repo: Annotated[TenantRepository, Depends(get_tenant_repository)],
) -> list[dict]:
    """Tenant manager: list every tenant. Admin-JWT-gated; TA → 403."""
    _require_tenant_manager(admin)
    rows = await repo.list_all() if hasattr(repo, "list_all") else []
    return [
        {
            "id": str(t.id),
            "name": t.name,
            "slug": getattr(t, "slug", None),
            "status": t.status,
            "plan": getattr(t, "plan", None),
            "created_at": t.created_at.isoformat() if t.created_at else None,
        }
        for t in rows
    ]


@platform_router.get("/audit-logs")
async def list_audit_logs_platform_scope(
    admin: Annotated[TenantAdminContext | None, Depends(require_admin_session)],
    repo: Annotated[TenantRepository, Depends(get_tenant_repository)],
    actor: str | None = None,
    tenant_id: UUID | None = None,
    action: str | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
) -> list[dict]:
    """Tenant manager: paginated platform-wide audit-log feed.

    Filterable by actor / tenant_id / action / date range. TA → 403.
    """
    _require_tenant_manager(admin)
    rows = await repo.list_audit_logs_platform_scope(
        actor=actor,
        tenant_id=tenant_id,
        action=action,
        date_from=date_from,
        date_to=date_to,
    )
    return [
        {
            "id": str(r.id),
            "tenant_id": str(r.tenant_id),
            "actor_id": r.actor_id,
            "actor_role": r.actor_role,
            "action": r.action,
            "metadata_json": r.metadata_json,
            "created_at": r.created_at.isoformat() if r.created_at else None,
        }
        for r in rows
    ]


def _require_tenant_manager(admin: TenantAdminContext | None) -> TenantAdminContext:
    if admin is None or admin.role != "tenant_manager":
        raise HTTPException(status_code=403, detail="forbidden")
    return admin


def _ensure_tenant_read_scope(
    path_tenant_id: UUID,
    admin: TenantAdminContext | None,
    authorization: str | None,
) -> None:
    """Allow either admin-JWT-on-own-tenant or widget-JWT-on-own-tenant."""
    if admin is not None and admin.tenant_id == path_tenant_id:
        return
    if authorization:
        scheme, _, token = authorization.partition(" ")
        if scheme.lower() == "bearer" and token:
            import jwt
            from app.services.widget_settings import widget_settings

            try:
                payload = jwt.decode(
                    token, widget_settings().widget_jwt_secret, algorithms=["HS256"]
                )
                widget_tid = payload.get("tenant_id")
                if isinstance(widget_tid, str) and UUID(widget_tid) == path_tenant_id:
                    return
            except Exception:  # noqa: BLE001 — any failure is a 403
                pass
    raise HTTPException(status_code=403, detail="forbidden")


@router.get("/{tenant_id}/usage")
async def get_tenant_usage_rollup(
    tenant_id: UUID,
    admin: Annotated[TenantAdminContext | None, Depends(require_admin_session)],
    repo: Annotated[TenantRepository, Depends(get_tenant_repository)],
    days: int = 30,
) -> dict:
    """Return a dashboard-shaped usage rollup for the caller's tenant.

    Window defaults to the last 30 days. Response shape is the one
    admin/usage_page.py expects (total_tokens, total_cost_usd, by_feature,
    daily_cost_usd).
    """
    _require_self_tenant(tenant_id, admin)
    safe_days = max(1, min(days, 365))
    # tenant_usage.created_at is a naive DateTime column (no tz); the comparison
    # parameter must be naive too or asyncpg raises "can't subtract offset-naive
    # and offset-aware datetimes".
    since = (datetime.now(UTC) - timedelta(days=safe_days)).replace(tzinfo=None)
    return await repo.usage_rollup(tenant_id, since=since)
