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
from app.db.rls import reset_tenant_context, set_tenant_context
from app.infra.redaction import redact_text


class EscalationCrossTenantError(RuntimeError):
    """The row that came back from INSERT did not carry the expected tenant_id."""


class EscalationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        *,
        tenant_id: UUID,
        conversation_id: UUID,
        reason: str,
        last_message_excerpt: str = "",
    ) -> EscalationTicket:
        """Insert a new escalation ticket for the given tenant.

        Applies redaction to free-text fields (Principle V) and sets the
        Postgres RLS context to ``tenant_id`` for the duration of the insert.
        Verifies the resulting row's ``tenant_id`` matches the supplied
        ``tenant_id`` as defense in depth against any session-context drift.
        """
        redacted_reason = redact_text(reason)
        redacted_excerpt = redact_text(last_message_excerpt)
        await set_tenant_context(self._session, tenant_id)
        try:
            ticket = EscalationTicket(
                tenant_id=tenant_id,
                conversation_id=conversation_id,
                reason=redacted_reason,
                status="open",
            )
            if redacted_excerpt:
                ticket.reason = f"{redacted_reason}\n\n[excerpt] {redacted_excerpt}".strip()
            self._session.add(ticket)
            await self._session.flush()
        finally:
            await reset_tenant_context(self._session)
        if ticket.tenant_id != tenant_id:
            raise EscalationCrossTenantError(
                "EscalationRepository.create inserted a row with a different tenant_id"
            )
        return ticket

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
