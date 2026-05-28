# Owner: Amer
"""Domain models for admin authentication."""

from __future__ import annotations

from uuid import UUID

from pydantic import BaseModel, EmailStr, Field


class AdminLoginRequest(BaseModel):
    """Request body for POST /admin/login."""

    email: EmailStr
    password: str = Field(min_length=1, max_length=255)


class AdminLoginResponse(BaseModel):
    """Successful login response.

    Mirrors the widget token shape: the client stores `token` in memory only
    and re-sends it as `Authorization: Bearer <token>` on every admin call.
    """

    token: str
    expires_in: int
    actor_id: str
    tenant_id: UUID
    role: str
    full_name: str | None = None
