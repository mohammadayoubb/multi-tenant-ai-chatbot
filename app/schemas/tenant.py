# Owner: Hiba
"""Tenant API request and response schemas."""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from app.domain.tenant import UsageFeature, UsageUnitType


class TenantCreateRequest(BaseModel):
    """Request body for Tenant Manager provisioning."""

    name: str = Field(min_length=1, max_length=255)


class TenantResponse(BaseModel):
    """Tenant metadata response."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    status: str
    created_at: datetime
    updated_at: datetime


class SuspendTenantRequest(BaseModel):
    """Request body for suspending a tenant."""

    reason: str | None = Field(default=None, max_length=1000)


class EraseTenantRequest(BaseModel):
    """Request body for erasing a tenant."""

    reason: str | None = Field(default=None, max_length=1000)


class ErasureResponse(BaseModel):
    """Tenant erasure response."""

    model_config = ConfigDict(from_attributes=True)

    tenant_id: UUID
    status: str
    deleted_rows: dict[str, int]
    deleted_blobs: int
    deleted_sessions: int
    trace_id: str


class UsageEventRequest(BaseModel):
    """Tenant-scoped usage event request."""

    feature: UsageFeature
    units: int = Field(gt=0)
    unit_type: UsageUnitType
    estimated_cost_usd: float = Field(ge=0)
    trace_id: str | None = Field(default=None, max_length=255)


class RateLimitResponse(BaseModel):
    """Tenant rate-limit check response."""

    model_config = ConfigDict(from_attributes=True)

    tenant_id: UUID
    action: str
    allowed: bool
    limit_count: int | None
    used: int
    remaining: int | None
    window_seconds: int | None
