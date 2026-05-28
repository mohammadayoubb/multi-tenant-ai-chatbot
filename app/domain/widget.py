# Owner: Amer
"""Pydantic domain models for the widget features.

Sources of truth:
- token exchange: specs/001-widget-token-exchange/data-model.md
- admin config: specs/004-widget-admin-config/data-model.md
"""

from __future__ import annotations

from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class WidgetTokenRequest(BaseModel):
    """Request body for POST /widgets/token (contracts/widget-token-endpoint.md)."""

    widget_id: UUID


class WidgetTokenResponse(BaseModel):
    """Success response for POST /widgets/token."""

    token: str
    expires_in: int
    session_id: UUID


class WidgetConfigDomain(BaseModel):
    """Server-side widget configuration row, joined with the owning tenant's status.

    `tenant_id` flows OUT of this lookup — the one acceptable read path where
    tenant identity is discovered rather than supplied. See feature-001 data-model
    §1 and Constitution Principle I.
    """

    id: UUID
    tenant_id: UUID
    widget_id: UUID
    allowed_origins: list[str]
    enabled: bool
    tenant_status: Literal["active", "suspended", "erasing", "erased"]
    # Added in feature 004 (admin config); free-form JSON object per /clarify Q3.
    theme_json: dict | None = None
    greeting: str | None = None


class WidgetTokenRefusalReason(str, Enum):
    """Internal refusal-reason bucket. NEVER exposed to clients (FR-007, FR-023)."""

    unknown_widget = "unknown_widget"
    origin_not_allowlisted = "origin_not_allowlisted"
    widget_disabled = "widget_disabled"
    tenant_not_active = "tenant_not_active"
    rate_limited_per_ip = "rate_limited_per_ip"
    rate_limited_per_widget = "rate_limited_per_widget"


class WidgetConfigResponse(BaseModel):
    """Response body for GET /widgets/config and PUT /widgets/config.

    tenant_id is deliberately omitted — the admin already knows their own
    tenant id (it is in their session); echoing it back is unnecessary.
    """

    widget_id: UUID
    allowed_origins: list[str]
    enabled: bool
    theme_json: dict | None
    greeting: str | None


class WidgetConfigUpdateRequest(BaseModel):
    """Request body for PUT /widgets/config.

    Validation rules:
    - allowed_origins: each item validated + normalized by a post-validator that
      reuses the same canonicalization the token endpoint applies. Invalid → 422.
    - enabled=True with empty allowed_origins (post-normalize) → 422.
    - greeting: <= 280 chars (Pydantic Field).
    - theme_json: any JSON object (dict) or null. Scalars / arrays → 422 (FR-015).
    - tenant_id MUST NOT appear in the body (extra='forbid').
    """

    model_config = ConfigDict(extra="forbid")

    allowed_origins: list[str]
    enabled: bool
    theme_json: dict | None = None
    greeting: str | None = Field(default=None, max_length=280)

    @field_validator("allowed_origins", mode="after")
    @classmethod
    def _normalize_origins(cls, origins: list[str]) -> list[str]:
        """Normalize + deduplicate; raise ValueError (→ 422) on any invalid item."""
        # Late import to avoid a circular dependency at module load.
        from app.services.widget_service import normalize_origin

        seen: set[str] = set()
        out: list[str] = []
        for raw in origins:
            try:
                canon = normalize_origin(raw)
            except ValueError as exc:
                raise ValueError(f"invalid origin: {raw!r}: {exc}") from exc
            if canon not in seen:
                seen.add(canon)
                out.append(canon)
        return out

    @model_validator(mode="after")
    def _enabled_requires_origins(self) -> "WidgetConfigUpdateRequest":
        if self.enabled and len(self.allowed_origins) == 0:
            raise ValueError(
                "enabled widget must have at least one allowed origin"
            )
        return self
