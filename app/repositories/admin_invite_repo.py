# Owner: Amer
"""Admin invite repository.

Acceptance flow (GET /admin/invites/{token}, POST .../accept) runs without
tenant context — the visitor has no JWT yet — so callers MUST pass a session
that bypasses RLS. The inviter flow (POST /admin/invites) runs under the
inviter's tenant context.
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminInvite


class AdminInviteRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        token: UUID,
        tenant_id: UUID,
        email: str,
        role: str,
        invited_by: str,
        expires_at: datetime,
    ) -> AdminInvite:
        invite = AdminInvite(
            token=token,
            tenant_id=tenant_id,
            email=email,
            role=role,
            invited_by=invited_by,
            expires_at=expires_at,
        )
        self._session.add(invite)
        await self._session.flush()
        return invite

    async def get_by_token(self, token: UUID) -> AdminInvite | None:
        result = await self._session.execute(
            select(AdminInvite).where(AdminInvite.token == token)
        )
        return result.scalar_one_or_none()

    async def mark_used(self, invite: AdminInvite, *, used_at: datetime) -> None:
        invite.used_at = used_at
        await self._session.flush()
