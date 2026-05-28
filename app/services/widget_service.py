# Owner: Amer
"""Widget services.

Two services share this module because they share a domain (widget) and an
owner (Amer):

- WidgetTokenService: POST /widgets/token. Validates origin against the
  tenant's allowlist, mints a short-lived JWT. See feature 001.
- WidgetConfigService: GET/PUT /widgets/config. Tenant-admin self-serve
  editor for allowed origins, greeting, theme, enabled. See feature 004.

Both services share normalize_origin so the admin save and the token endpoint
cannot drift on what counts as a valid origin.

Constitution principles enforced:
- I (Tenant Isolation): tenant_id derived from the repository row or from the
  trusted role dep, never from a request body.
- II (Layered Architecture): services own business logic; routes own HTTP;
  repos own SQL.
- IV (Defense-in-Depth Auth): HS256 JWT with origin binding for tokens; role
  gate plus tenant scoping for admin config.
- V (Lean Serving & Redaction): logs use hashed identifiers via widget_logging.
- VII (Clean & Simple Code): one validation pipeline; one normalization helper
  used by both halves; no premature abstractions.
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import jwt

from app.domain.widget import (
    WidgetConfigDomain,
    WidgetConfigUpdateRequest,
    WidgetTokenRefusalReason,
    WidgetTokenResponse,
)
from app.repositories.widget_repo import WidgetRepository
from app.services.rate_limiter import RateLimiter
from app.services.widget_logging import emit_issuance, emit_refusal, widget_trace_span
from app.services.widget_settings import widget_settings

# Default ports per scheme — used by origin canonicalization so that
# https://example.com and https://example.com:443 are treated as equal.
_DEFAULT_PORTS = {"http": 80, "https": 443}


class TokenRefused(Exception):
    """Internal signal: issuance MUST fail. Every TokenRefused maps to the
    same byte-identical 403 at the route boundary (FR-007, FR-008, FR-017)."""

    def __init__(self, reason: WidgetTokenRefusalReason) -> None:
        super().__init__(reason.value)
        self.reason = reason


@dataclass
class WidgetTokenService:
    repo: WidgetRepository
    per_ip_limiter: RateLimiter
    per_widget_limiter: RateLimiter

    async def issue_token(
        self, *, widget_id: UUID, origin: str, source_ip: str
    ) -> WidgetTokenResponse:
        """Issue a token or raise TokenRefused.

        Wrapped in a trace span (FR-022). Every refusal path runs the repository
        lookup before returning (FR-008a, timing discipline).
        """
        with widget_trace_span(origin) as span:
            started_perf = time.perf_counter()

            # FR-008a: always perform the widget lookup, even when other checks
            # will reject. This denies the attacker a gross timing signal.
            config = await self.repo.get_by_widget_id(widget_id)
            tenant_id_for_log = config.tenant_id if config is not None else None

            # Per-IP rate baseline (FR-015).
            if not await self.per_ip_limiter.check(source_ip):
                self._refuse(
                    reason=WidgetTokenRefusalReason.rate_limited_per_ip,
                    widget_id=widget_id,
                    source_ip=source_ip,
                    origin=origin,
                    started_perf=started_perf,
                    tenant_id=tenant_id_for_log,
                    span=span,
                )

            # Per-widget rate baseline (FR-016).
            if not await self.per_widget_limiter.check(str(widget_id)):
                self._refuse(
                    reason=WidgetTokenRefusalReason.rate_limited_per_widget,
                    widget_id=widget_id,
                    source_ip=source_ip,
                    origin=origin,
                    started_perf=started_perf,
                    tenant_id=tenant_id_for_log,
                    span=span,
                )

            # Validation gates.
            if config is None:
                self._refuse(
                    reason=WidgetTokenRefusalReason.unknown_widget,
                    widget_id=widget_id,
                    source_ip=source_ip,
                    origin=origin,
                    started_perf=started_perf,
                    tenant_id=None,
                    span=span,
                )
            assert config is not None  # for type checkers; _refuse raises
            if not config.enabled:
                self._refuse(
                    reason=WidgetTokenRefusalReason.widget_disabled,
                    widget_id=widget_id,
                    source_ip=source_ip,
                    origin=origin,
                    started_perf=started_perf,
                    tenant_id=config.tenant_id,
                    span=span,
                )
            if config.tenant_status != "active":
                self._refuse(
                    reason=WidgetTokenRefusalReason.tenant_not_active,
                    widget_id=widget_id,
                    source_ip=source_ip,
                    origin=origin,
                    started_perf=started_perf,
                    tenant_id=config.tenant_id,
                    span=span,
                )

            canonical_request_origin = _canonicalize_origin(origin)
            canonical_allowed = {
                co
                for co in (_canonicalize_origin(o) for o in config.allowed_origins)
                if co is not None
            }
            if (
                canonical_request_origin is None
                or canonical_request_origin not in canonical_allowed
            ):
                self._refuse(
                    reason=WidgetTokenRefusalReason.origin_not_allowlisted,
                    widget_id=widget_id,
                    source_ip=source_ip,
                    origin=origin,
                    started_perf=started_perf,
                    tenant_id=config.tenant_id,
                    span=span,
                )

            # Success.
            session_id = uuid4()
            assert canonical_request_origin is not None  # narrowed above
            token = self._mint_jwt(
                tenant_id=config.tenant_id,
                widget_id=config.widget_id,
                origin=canonical_request_origin,
                session_id=session_id,
            )
            latency_ms = int((time.perf_counter() - started_perf) * 1000)
            span["outcome"] = "issued"
            span["tenant_id"] = str(config.tenant_id)
            emit_issuance(
                tenant_id=config.tenant_id,
                widget_id=widget_id,
                source_ip=source_ip,
                origin=origin,
                latency_ms=latency_ms,
            )
            return WidgetTokenResponse(
                token=token,
                expires_in=widget_settings().widget_token_ttl_seconds,
                session_id=session_id,
            )

    # --- helpers ---

    def _refuse(
        self,
        *,
        reason: WidgetTokenRefusalReason,
        widget_id: UUID,
        source_ip: str,
        origin: str,
        started_perf: float,
        tenant_id: UUID | None,
        span: dict[str, object],
    ) -> None:
        latency_ms = int((time.perf_counter() - started_perf) * 1000)
        span["outcome"] = "refused"
        span["outcome.reason"] = reason.value
        if tenant_id is not None:
            span["tenant_id"] = str(tenant_id)
        emit_refusal(
            reason=reason,
            widget_id=widget_id,
            source_ip=source_ip,
            origin=origin,
            latency_ms=latency_ms,
            tenant_id=tenant_id,
        )
        raise TokenRefused(reason)

    def _mint_jwt(
        self,
        *,
        tenant_id: UUID,
        widget_id: UUID,
        origin: str,
        session_id: UUID,
    ) -> str:
        now = int(time.time())
        ttl = widget_settings().widget_token_ttl_seconds
        payload = {
            "tenant_id": str(tenant_id),
            "widget_id": str(widget_id),
            "origin": origin,
            "session_id": str(session_id),
            "iat": now,
            "exp": now + ttl,
        }
        return jwt.encode(
            payload, widget_settings().widget_jwt_secret, algorithm="HS256"
        )


def normalize_origin(raw: str) -> str:
    """Canonical form of a tenant-supplied origin string. Used by both the
    admin save path (feature 004) and the token endpoint (feature 001).

    Lowercases scheme + host; strips default ports (80 for http, 443 for https);
    strips path/query/fragment/userinfo. Raises ValueError on any non-http(s)
    scheme, missing host, or malformed input.

    Implemented as a wrapper around _canonicalize_origin so the admin and the
    token endpoint cannot drift — both must accept and reject the same origins.
    """
    canon = _canonicalize_origin(raw)
    if canon is None:
        raise ValueError(f"invalid origin: {raw!r}")
    return canon


def _canonicalize_origin(origin: str) -> str | None:
    """Return scheme://host[:port] with lowercased host and default port stripped.

    Returns None for unparseable, non-http(s), or hostless inputs.
    No subdomain rollup; the input must match an allowlist entry on the exact
    scheme+host+port triple (FR-002).
    """
    try:
        parts = urlsplit(origin)
    except ValueError:
        return None
    if parts.scheme not in ("http", "https"):
        return None
    if not parts.hostname:
        return None
    host = parts.hostname.lower()
    try:
        port = parts.port
    except ValueError:
        return None
    if port is None or port == _DEFAULT_PORTS.get(parts.scheme):
        return f"{parts.scheme}://{host}"
    return f"{parts.scheme}://{host}:{port}"


# -----------------------------------------------------------------------------
# Feature 004: Tenant Admin Widget Configuration
# -----------------------------------------------------------------------------


class AuditLogger(Protocol):
    """Single-method Protocol matching TenantRepository.add_audit_log signature.

    See specs/004-widget-admin-config/contracts/audit-log-consumption.md.
    Hiba's TenantRepository implements this Protocol incidentally; this
    feature's service depends on the Protocol so tests can use a fake.
    """

    async def add_audit_log(
        self,
        tenant_id: UUID,
        actor_role: str,
        action: str,
        actor_id: str | None = None,
        metadata: dict | None = None,
    ) -> None: ...


class WidgetConfigNotFound(Exception):
    """No widget_configs row exists for the caller's tenant.

    Route maps this to 403 (indistinguishable from role-missing) to prevent
    tenant-existence enumeration (Principle I, contract clause E1/E3).
    """


@dataclass
class WidgetConfigService:
    """Tenant-admin widget configuration service.

    All public methods take a trusted tenant_id derived from the role dep.
    Origin diff + audit log calls are produced from the service layer so the
    route stays thin (Principle II).
    """

    repo: WidgetRepository
    audit_logger: AuditLogger

    async def get_for_tenant(self, tenant_id: UUID) -> WidgetConfigDomain:
        row = await self.repo.get_by_tenant_id(tenant_id)
        if row is None:
            raise WidgetConfigNotFound()
        return row

    async def update_widget_config(
        self,
        tenant_id: UUID,
        request: WidgetConfigUpdateRequest,
        actor_id: str | None,
    ) -> WidgetConfigDomain:
        """Apply the update + emit one audit log entry per net origin change.

        Transactional behavior: the InMemoryWidgetRepository snapshot is captured
        before the update; if any audit log call raises, the previous snapshot
        is restored and the exception propagates. The route turns the exception
        into a 500. (For the future SQL backend, this becomes the standard
        async with session.begin() wrap.)
        """
        previous = await self.repo.get_by_tenant_id(tenant_id)
        if previous is None:
            raise WidgetConfigNotFound()

        previous_origins: set[str] = set(previous.allowed_origins)
        new_origins: set[str] = set(request.allowed_origins)
        added: list[str] = sorted(new_origins - previous_origins)
        removed: list[str] = sorted(previous_origins - new_origins)

        # Snapshot for rollback (InMemory path).
        snapshot = previous.model_copy(deep=True)

        updated = await self.repo.update_by_tenant_id(
            tenant_id,
            allowed_origins=request.allowed_origins,
            enabled=request.enabled,
            theme_json=request.theme_json,
            greeting=request.greeting,
        )
        if updated is None:
            # Race: row disappeared between fetch and update. Treat as not-found.
            raise WidgetConfigNotFound()

        try:
            for origin in added:
                await self.audit_logger.add_audit_log(
                    tenant_id=tenant_id,
                    actor_role="tenant_admin",
                    action="widget.origin_added",
                    actor_id=actor_id,
                    metadata={
                        "origin": origin,
                        "widget_id": str(updated.widget_id),
                    },
                )
            for origin in removed:
                await self.audit_logger.add_audit_log(
                    tenant_id=tenant_id,
                    actor_role="tenant_admin",
                    action="widget.origin_removed",
                    actor_id=actor_id,
                    metadata={
                        "origin": origin,
                        "widget_id": str(updated.widget_id),
                    },
                )
        except Exception:
            # Roll back the InMemory write so FR-013 holds.
            await self.repo.update_by_tenant_id(
                tenant_id,
                allowed_origins=snapshot.allowed_origins,
                enabled=snapshot.enabled,
                theme_json=snapshot.theme_json,
                greeting=snapshot.greeting,
            )
            raise

        return updated
