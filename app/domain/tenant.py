# Owner: Hiba
"""Tenant domain models."""

from datetime import datetime
from enum import StrEnum
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class PlatformRole(StrEnum):
    """Platform-level roles used for tenant management."""

    TENANT_MANAGER = "tenant_manager"
    TENANT_ADMIN = "tenant_admin"
    MEMBER = "member"
    VISITOR = "visitor"


class TenantStatus(StrEnum):
    """Supported tenant lifecycle statuses."""

    ACTIVE = "active"
    SUSPENDED = "suspended"
    ERASING = "erasing"
    ERASED = "erased"


class UsageFeature(StrEnum):
    """Tenant usage buckets used for cost and rate-limit accounting."""

    CHAT = "chat"
    EMBEDDING = "embedding"
    CLASSIFIER = "classifier"
    RAG = "rag"
    AGENT = "agent"
    GUARDRAILS = "guardrails"


class UsageUnitType(StrEnum):
    """Supported usage unit types."""

    TOKENS = "tokens"
    REQUESTS = "requests"
    SECONDS = "seconds"


class TenantCreate(BaseModel):
    """Tenant provisioning input."""

    name: str = Field(min_length=1, max_length=255)


class TenantDomain(BaseModel):
    """Safe tenant response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    name: str
    status: str
    created_at: datetime
    updated_at: datetime


class AuditLogDomain(BaseModel):
    """Tenant-scoped audit log response model."""

    model_config = ConfigDict(from_attributes=True)

    id: UUID
    tenant_id: UUID
    actor_id: str | None
    actor_role: str
    action: str
    metadata_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class UsageEvent(BaseModel):
    """Per-tenant usage event for cost attribution."""

    feature: UsageFeature | str
    units: int = Field(gt=0)
    unit_type: UsageUnitType | str
    estimated_cost_usd: float = Field(ge=0)
    trace_id: str | None = None


class RateLimitResult(BaseModel):
    """Result of checking a tenant-scoped rate limit."""

    tenant_id: UUID
    action: str
    allowed: bool
    limit_count: int | None
    used: int
    remaining: int | None
    window_seconds: int | None


class ErasureResult(BaseModel):
    """Tenant erasure result returned to Tenant Manager workflows."""

    tenant_id: UUID
    status: str
    deleted_rows: dict[str, int]
    deleted_blobs: int = 0
    deleted_sessions: int = 0
    trace_id: str
