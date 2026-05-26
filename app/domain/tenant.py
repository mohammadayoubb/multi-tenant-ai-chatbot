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
