# Owner: Nasser
"""Escalation ticket repository.

All reads/writes are tenant-scoped — the route layer is responsible for
deriving `tenant_id` from the JWT before calling in. RLS on the table is
the second line of defense.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import EscalationTicket


class EscalationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_by_tenant(self, tenant_id: UUID) -> list[EscalationTicket]:
        result = await self._session.execute(
            select(EscalationTicket)
            .where(EscalationTicket.tenant_id == tenant_id)
            .order_by(EscalationTicket.created_at.desc())
        )
        return list(result.scalars().all())

    async def get(self, ticket_id: UUID) -> EscalationTicket | None:
        result = await self._session.execute(
            select(EscalationTicket).where(EscalationTicket.id == ticket_id)
        )
        return result.scalar_one_or_none()

    async def update_status_and_assignee(
        self,
        ticket_id: UUID,
        *,
        status: str | None,
        assignee_id: str | None,
        update_assignee: bool,
    ) -> EscalationTicket | None:
        ticket = await self.get(ticket_id)
        if ticket is None:
            return None
        if status is not None:
            ticket.status = status
        if update_assignee:
            ticket.assigned_to = assignee_id
        await self._session.flush()
        return ticket
