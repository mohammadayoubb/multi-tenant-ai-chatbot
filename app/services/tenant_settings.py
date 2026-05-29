# Owner: Hiba
"""Tenant settings service — Tenant Manager scope only.

Only the tenant_manager role may PUT these values. Validation bounds:

- default_invite_ttl_seconds: 3600 .. 30 * 24 * 3600
- rate_limit_chat_per_minute:  1 .. 1000
- rate_limit_token_per_minute: 1 .. 1000

Successful update emits a `tenant_settings_updated` audit event with
non-sensitive metadata only (no PII).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.repositories.tenant_repo import TenantRepository
from app.repositories.tenant_settings_repo import TenantSettingsRepository


class TenantSettingsForbidden(Exception):
    """Caller is not a tenant_manager."""


class TenantSettingsInvalid(Exception):
    """Submitted body failed validation bounds."""


_TTL_MIN = 3600
_TTL_MAX = 30 * 24 * 3600
_RATE_MIN = 1
_RATE_MAX = 1000


class TenantSettingsBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    default_invite_ttl_seconds: int = Field(ge=_TTL_MIN, le=_TTL_MAX)
    rate_limit_chat_per_minute: int = Field(ge=_RATE_MIN, le=_RATE_MAX)
    rate_limit_token_per_minute: int = Field(ge=_RATE_MIN, le=_RATE_MAX)


@dataclass(frozen=True)
class TenantSettingsActor:
    tenant_id: UUID
    actor_id: str
    role: str


class TenantSettingsService:
    def __init__(
        self,
        repo: TenantSettingsRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self._repo = repo
        self._tenant_repo = tenant_repo

    async def get_for_tenant(self, tenant_id: UUID) -> dict[str, Any]:
        row = await self._repo.get_or_create(tenant_id)
        return _to_payload(row)

    async def update_for_tenant(
        self,
        tenant_id: UUID,
        body: dict[str, Any],
        actor: TenantSettingsActor,
    ) -> dict[str, Any]:
        if actor.role != "tenant_manager":
            raise TenantSettingsForbidden("tenant_manager only")
        try:
            validated = TenantSettingsBody.model_validate(body)
        except ValidationError as exc:
            raise TenantSettingsInvalid(str(exc)) from exc
        row = await self._repo.update(tenant_id, validated.model_dump())
        await self._tenant_repo.add_audit_log(
            tenant_id=tenant_id,
            actor_id=actor.actor_id,
            actor_role=actor.role,
            action="tenant_settings_updated",
            metadata={
                "default_invite_ttl_seconds": row.default_invite_ttl_seconds,
                "rate_limit_chat_per_minute": row.rate_limit_chat_per_minute,
                "rate_limit_token_per_minute": row.rate_limit_token_per_minute,
            },
        )
        return _to_payload(row)


def _to_payload(row) -> dict[str, Any]:  # noqa: ANN001 — row is the ORM model
    return {
        "tenant_id": str(row.tenant_id),
        "default_invite_ttl_seconds": row.default_invite_ttl_seconds,
        "rate_limit_chat_per_minute": row.rate_limit_chat_per_minute,
        "rate_limit_token_per_minute": row.rate_limit_token_per_minute,
    }
