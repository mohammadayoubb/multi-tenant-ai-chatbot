"""Tenant settings request/response schemas (010 T064).

`TenantSettingsPutRequest` is the contract for ``PUT /tenants/{tid}/settings``.
Field clamps mirror data-model.md §`tenant_settings`:

- ``default_invite_ttl_seconds``: 3600 .. 2592000 (1h to 30 days)
- ``rate_limit_chat_per_minute``: 1 .. 600
- ``rate_limit_token_per_minute``: 1 .. 600
- ``rate_limit_lead_per_session``: 1 .. 50 (optional; new in 0006)

The route layer keeps the existing inline validation in `TenantSettingsBody`
(app/services/tenant_settings.py) for backwards compatibility with the
in-flight tests. This schema is the authoritative contract referenced by
the OpenAPI doc and the integration tests in
``tests/integration/test_tenant_settings_endpoint.py``.

`extra="forbid"` rejects smuggled identity fields (`tenant_id`, `actor_id`,
`role`, `created_at`, `updated_at`) with HTTP 422.
"""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


_TTL_MIN = 3600
_TTL_MAX = 30 * 24 * 3600
_RATE_MIN = 1
_RATE_MAX = 600
_LEAD_MIN = 1
_LEAD_MAX = 50


class TenantSettingsPutRequest(BaseModel):
    """Body for ``PUT /tenants/{tid}/settings`` — tenant_manager only."""

    model_config = ConfigDict(extra="forbid")

    default_invite_ttl_seconds: int = Field(ge=_TTL_MIN, le=_TTL_MAX)
    rate_limit_chat_per_minute: int = Field(ge=_RATE_MIN, le=_RATE_MAX)
    rate_limit_token_per_minute: int = Field(ge=_RATE_MIN, le=_RATE_MAX)
    rate_limit_lead_per_session: int | None = Field(
        default=None, ge=_LEAD_MIN, le=_LEAD_MAX
    )


class TenantSettingsResponse(BaseModel):
    """Shape returned by ``GET /tenants/{tid}/settings`` and the PUT echo."""

    model_config = ConfigDict(extra="forbid")

    tenant_id: UUID
    default_invite_ttl_seconds: int
    rate_limit_chat_per_minute: int
    rate_limit_token_per_minute: int
    rate_limit_lead_per_session: int | None = None
