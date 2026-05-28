# Owner: Amer
"""Widget loader, token exchange, and tenant-admin config routes.

- POST /widgets/token  — feature 001, see specs/001-widget-token-exchange/.
- GET  /widgets/config — feature 004, see specs/004-widget-admin-config/.
- PUT  /widgets/config — feature 004, see specs/004-widget-admin-config/.
"""

from __future__ import annotations

import json
from functools import lru_cache

from fastapi import APIRouter, Depends, Request
from fastapi.responses import Response
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import TenantAdminContext, require_tenant_admin
from app.db.session import get_session
from app.domain.widget import (
    WidgetConfigResponse,
    WidgetConfigUpdateRequest,
    WidgetTokenRequest,
)
from app.repositories.tenant_repo import TenantRepository
from app.repositories.widget_repo import WidgetRepository, get_widget_repository
from app.services.rate_limiter import (
    RateLimiter,
    per_ip_rate_limiter,
    per_widget_rate_limiter,
)
from app.services.widget_service import (
    AuditLogger,
    TokenRefused,
    WidgetConfigNotFound,
    WidgetConfigService,
    WidgetTokenService,
)

router = APIRouter(prefix="/widgets", tags=["widgets"])


# Rate limiters are process-cached so the token-bucket state survives across
# requests; the repo is now request-scoped (SQL backend needs a per-request
# session), so the service is constructed per request from the cached limiters
# + the freshly-bound repo.
@lru_cache(maxsize=1)
def _cached_per_ip_limiter() -> RateLimiter:
    return per_ip_rate_limiter()


@lru_cache(maxsize=1)
def _cached_per_widget_limiter() -> RateLimiter:
    return per_widget_rate_limiter()


def get_widget_token_service(
    repo: WidgetRepository = Depends(get_widget_repository),
) -> WidgetTokenService:
    return WidgetTokenService(
        repo=repo,
        per_ip_limiter=_cached_per_ip_limiter(),
        per_widget_limiter=_cached_per_widget_limiter(),
    )


def get_audit_logger(
    session: AsyncSession = Depends(get_session),
) -> AuditLogger:
    """Return a request-scoped audit logger.

    `TenantRepository` implements the `AuditLogger` Protocol incidentally
    (matching `add_audit_log` signature); binding to the request session means
    audit rows commit/rollback with the rest of the unit of work.
    """
    return TenantRepository(session)


def get_widget_config_service(
    repo: WidgetRepository = Depends(get_widget_repository),
    audit_logger: AuditLogger = Depends(get_audit_logger),
) -> WidgetConfigService:
    return WidgetConfigService(
        repo=repo,
        audit_logger=audit_logger,
    )


# FR-007, FR-008, FR-017: every refusal returns this exact body.
_REFUSAL_BODY_BYTES = b'{"error":"widget_unavailable"}'
_BAD_REQUEST_BODY_BYTES = b'{"error":"bad_request"}'
_COMMON_HEADERS = {
    "Cache-Control": "no-store",
    "Content-Type": "application/json",
}


def _byte_response(status_code: int, body_bytes: bytes) -> Response:
    """Return a Response whose body is the exact bytes passed in.

    Avoids JSON-encoder variability (whitespace, key order) that would break
    the byte-equality guarantee in SC-002.
    """
    return Response(
        status_code=status_code, content=body_bytes, headers=_COMMON_HEADERS
    )


def _refusal_response() -> Response:
    return _byte_response(403, _REFUSAL_BODY_BYTES)


def _bad_request_response() -> Response:
    return _byte_response(400, _BAD_REQUEST_BODY_BYTES)


@router.post("/token")
async def exchange_widget_token(
    request: Request,
    service: WidgetTokenService = Depends(get_widget_token_service),
) -> Response:
    """Exchange widget_id and origin for a signed short-lived token."""
    origin = request.headers.get("Origin")
    if not origin:
        return _bad_request_response()

    try:
        raw = await request.json()
    except json.JSONDecodeError:
        return _bad_request_response()

    try:
        body = WidgetTokenRequest.model_validate(raw)
    except ValidationError:
        return _bad_request_response()

    source_ip = request.client.host if request.client else "0.0.0.0"
    try:
        result = await service.issue_token(
            widget_id=body.widget_id, origin=origin, source_ip=source_ip
        )
    except TokenRefused:
        return _refusal_response()

    # Encode the success body once; success responses don't need byte-equality discipline.
    payload = result.model_dump(mode="json")
    return Response(
        status_code=200,
        content=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers=_COMMON_HEADERS,
    )


# -----------------------------------------------------------------------------
# Feature 004: Tenant Admin Widget Configuration
# -----------------------------------------------------------------------------

_ADMIN_FORBIDDEN_BODY = b'{"error":"forbidden"}'
_ADMIN_INTERNAL_BODY = b'{"error":"internal"}'


def _admin_forbidden() -> Response:
    """Indistinguishable 403 for role-missing and row-not-found cases (E1, E3)."""
    return _byte_response(403, _ADMIN_FORBIDDEN_BODY)


def _admin_internal() -> Response:
    """Audit-rollback 500. Does not echo server-side details (contract E2)."""
    return _byte_response(500, _ADMIN_INTERNAL_BODY)


def _admin_response(row) -> Response:
    payload = WidgetConfigResponse(
        widget_id=row.widget_id,
        allowed_origins=row.allowed_origins,
        enabled=row.enabled,
        theme_json=row.theme_json,
        greeting=row.greeting,
    ).model_dump(mode="json")
    return Response(
        status_code=200,
        content=json.dumps(payload, separators=(",", ":")).encode("utf-8"),
        headers=_COMMON_HEADERS,
    )


@router.get("/config")
async def get_widget_config(
    admin: TenantAdminContext | None = Depends(require_tenant_admin),
    service: WidgetConfigService = Depends(get_widget_config_service),
) -> Response:
    """Return the current widget configuration for the calling admin's tenant."""
    if admin is None:
        return _admin_forbidden()
    try:
        row = await service.get_for_tenant(admin.tenant_id)
    except WidgetConfigNotFound:
        return _admin_forbidden()
    return _admin_response(row)


@router.put("/config")
async def put_widget_config(
    request: Request,
    admin: TenantAdminContext | None = Depends(require_tenant_admin),
    service: WidgetConfigService = Depends(get_widget_config_service),
) -> Response:
    """Apply a widget configuration update for the calling admin's tenant.

    422 on validation failure; 403 on cross-tenant or missing row; 500 on
    audit-rollback path (raised by the service, surfaced by FastAPI's default
    exception handler).
    """
    if admin is None:
        return _admin_forbidden()
    try:
        raw = await request.json()
    except json.JSONDecodeError:
        # JSON-safe validation error envelope.
        return Response(
            status_code=422,
            content=b'{"detail":[{"msg":"invalid JSON body","type":"json_invalid"}]}',
            headers=_COMMON_HEADERS,
        )
    try:
        body = WidgetConfigUpdateRequest.model_validate(raw)
    except ValidationError as exc:
        # exc.errors() can contain non-JSON-serializable objects (the original
        # ValueError instance from field_validators). exc.json() returns the
        # same data as a guaranteed-JSON-safe string.
        return Response(
            status_code=422,
            content=(b'{"detail":' + exc.json().encode("utf-8") + b'}'),
            headers=_COMMON_HEADERS,
        )
    try:
        updated = await service.update_widget_config(
            admin.tenant_id, body, admin.actor_id
        )
    except WidgetConfigNotFound:
        return _admin_forbidden()
    except Exception:
        # FR-013: audit-log failure rolls back the row (service handles rollback)
        # and surfaces here as an unhandled exception. Return the canonical 500
        # body; do not echo server-side details (contract E2).
        return _admin_internal()
    return _admin_response(updated)
