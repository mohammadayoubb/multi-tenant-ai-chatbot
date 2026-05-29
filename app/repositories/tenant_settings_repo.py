# Owner: Hiba
"""Tenant settings repository.

One row per tenant. First read materializes the defaults; subsequent reads
return the live row. UPDATE is field-by-field — the service layer chooses
which subset to send.
"""

from __future__ import annotations

from typing import Any
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import TenantSettings


class TenantSettingsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_or_create(self, tenant_id: UUID) -> TenantSettings:
        """Return the tenant's settings row, creating one with defaults if absent."""
        result = await self._session.execute(
            select(TenantSettings).where(TenantSettings.tenant_id == tenant_id)
        )
        row = result.scalar_one_or_none()
        if row is None:
            row = TenantSettings(tenant_id=tenant_id)
            self._session.add(row)
            await self._session.flush()
        return row

    async def update(
        self, tenant_id: UUID, body: dict[str, Any]
    ) -> TenantSettings:
        row = await self.get_or_create(tenant_id)
        if "default_invite_ttl_seconds" in body:
            row.default_invite_ttl_seconds = int(body["default_invite_ttl_seconds"])
        if "rate_limit_chat_per_minute" in body:
            row.rate_limit_chat_per_minute = int(body["rate_limit_chat_per_minute"])
        if "rate_limit_token_per_minute" in body:
            row.rate_limit_token_per_minute = int(body["rate_limit_token_per_minute"])
        await self._session.flush()
        return row
