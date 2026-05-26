# Owner: Amer
"""Pydantic domain models for the widget token exchange feature.

Source of truth: specs/001-widget-token-exchange/data-model.md
"""

from __future__ import annotations

from enum import Enum
from typing import Literal
from uuid import UUID

from pydantic import BaseModel


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
    tenant identity is discovered rather than supplied. See data-model.md §1
    and Constitution Principle I.
    """

    id: UUID
    tenant_id: UUID
    widget_id: UUID
    allowed_origins: list[str]
    enabled: bool
    tenant_status: Literal["active", "suspended", "erasing", "erased"]


class WidgetTokenRefusalReason(str, Enum):
    """Internal refusal-reason bucket. NEVER exposed to clients (FR-007, FR-023)."""

    unknown_widget = "unknown_widget"
    origin_not_allowlisted = "origin_not_allowlisted"
    widget_disabled = "widget_disabled"
    tenant_not_active = "tenant_not_active"
    rate_limited_per_ip = "rate_limited_per_ip"
    rate_limited_per_widget = "rate_limited_per_widget"
