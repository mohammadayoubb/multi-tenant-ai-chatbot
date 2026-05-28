# Owner: Amer
"""Domain models for the admin invite flow."""

from __future__ import annotations

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, EmailStr, Field

InviteRole = Literal["tenant_admin", "tenant_manager"]


class InviteCreateRequest(BaseModel):
    """POST /admin/invites — request body sent by an authenticated admin."""

    email: EmailStr
    role: InviteRole = "tenant_admin"
    ttl_seconds: int = Field(default=86400 * 7, ge=60, le=86400 * 30)


class InviteCreateResponse(BaseModel):
    """Returned to the inviter so they can copy/paste the acceptance link."""

    token: UUID
    email: EmailStr
    role: InviteRole
    tenant_id: UUID
    expires_at: datetime


class InviteDetailsResponse(BaseModel):
    """GET /admin/invites/{token} — public, safe metadata only.

    Intentionally excludes `invited_by`, `tenant_id`, and any other field that
    would leak platform structure to an attacker holding a stolen token.
    """

    email: EmailStr
    role: InviteRole
    tenant_name: str
    expires_at: datetime
    status: Literal["pending", "used", "expired"]


class InviteAcceptRequest(BaseModel):
    """POST /admin/invites/{token}/accept — the visitor's submission.

    Notice: NO `tenant_id`, NO `role`, NO `email` field. The server reads all
    three from the invite row keyed by the URL token. The accept form on the
    frontend never lets the visitor type those fields either.
    """

    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=255)
    confirm_password: str = Field(min_length=8, max_length=255)
