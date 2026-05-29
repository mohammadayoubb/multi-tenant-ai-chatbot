# Owner: Nasser
"""Escalation service.

List + patch over EscalationTicket rows. Scoping rules:

- list_for_tenant(tid): only the JWT tenant.
- patch(ticket_id, ...): the ticket MUST belong to the JWT tenant (403).
- assignee_id MUST resolve to an admin_users row with the same tenant_id
  (422). Both lookups happen here; the route is thin.

Status transitions:
- allowed values: pending | in_progress | resolved (per missing-endpoints §4).
  The DB check constraint also permits "open" and "erased"; we accept the
  contract values and silently treat the DB "open" as the legacy synonym
  for "pending" on read.

Audit events:
- escalation.status_changed     when status mutates
- escalation.assignee_changed   when assignee mutates
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.repositories.admin_user_repo import AdminUserRepository
from app.repositories.escalation_repo import EscalationRepository
from app.repositories.tenant_repo import TenantRepository


class EscalationForbidden(Exception):
    """Ticket belongs to a different tenant."""


class EscalationNotFound(Exception):
    """Ticket id is unknown."""


class EscalationInvalid(Exception):
    """Body failed validation (bad status, unknown / cross-tenant assignee)."""


_ALLOWED_STATUSES = ("pending", "in_progress", "resolved", "open")


class EscalationPatchBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: str | None = Field(default=None)
    assignee_id: str | None = Field(default=None)

    def has_assignee_field(self, raw: dict[str, Any]) -> bool:
        """True when the inbound body sent `assignee_id` (even if null)."""
        return "assignee_id" in raw


@dataclass(frozen=True)
class EscalationActor:
    tenant_id: UUID
    actor_id: str
    role: str


class EscalationService:
    def __init__(
        self,
        repo: EscalationRepository,
        admin_user_repo: AdminUserRepository,
        tenant_repo: TenantRepository,
    ) -> None:
        self._repo = repo
        self._admin_user_repo = admin_user_repo
        self._tenant_repo = tenant_repo

    async def list_for_tenant(self, tenant_id: UUID) -> list[dict[str, Any]]:
        rows = await self._repo.list_by_tenant(tenant_id)
        return [_to_payload(r, assignee_name=None) for r in rows]

    async def patch(
        self,
        ticket_id: UUID,
        body: dict[str, Any],
        actor: EscalationActor,
    ) -> dict[str, Any]:
        try:
            validated = EscalationPatchBody.model_validate(body)
        except ValidationError as exc:
            raise EscalationInvalid(str(exc)) from exc
        if validated.status is not None and validated.status not in _ALLOWED_STATUSES:
            raise EscalationInvalid(f"status must be one of {_ALLOWED_STATUSES}")

        ticket = await self._repo.get(ticket_id)
        if ticket is None:
            raise EscalationNotFound("unknown")
        if ticket.tenant_id != actor.tenant_id:
            raise EscalationForbidden("cross_tenant")

        update_assignee = validated.has_assignee_field(body)
        assignee_name: str | None = None
        if update_assignee and validated.assignee_id:
            try:
                assignee_uuid = UUID(validated.assignee_id)
            except ValueError as exc:
                raise EscalationInvalid("assignee_id must be a UUID") from exc
            assignee = await self._admin_user_repo.get_by_id(assignee_uuid)
            if assignee is None or assignee.tenant_id != actor.tenant_id:
                raise EscalationInvalid("assignee_id does not belong to this tenant")
            assignee_name = assignee.full_name or assignee.email

        previous_status = ticket.status
        previous_assignee = ticket.assigned_to
        updated = await self._repo.update_status_and_assignee(
            ticket_id,
            status=validated.status,
            assignee_id=validated.assignee_id if update_assignee else None,
            update_assignee=update_assignee,
        )
        assert updated is not None

        if validated.status is not None and validated.status != previous_status:
            await self._tenant_repo.add_audit_log(
                tenant_id=actor.tenant_id,
                actor_id=actor.actor_id,
                actor_role=actor.role,
                action="escalation.status_changed",
                metadata={
                    "ticket_id": str(ticket_id),
                    "from": previous_status,
                    "to": validated.status,
                },
            )
        if update_assignee and validated.assignee_id != previous_assignee:
            await self._tenant_repo.add_audit_log(
                tenant_id=actor.tenant_id,
                actor_id=actor.actor_id,
                actor_role=actor.role,
                action="escalation.assignee_changed",
                metadata={
                    "ticket_id": str(ticket_id),
                    "assignee_id": validated.assignee_id,
                },
            )

        return _to_payload(updated, assignee_name=assignee_name)


def _to_payload(ticket, *, assignee_name: str | None) -> dict[str, Any]:  # noqa: ANN001
    return {
        "ticket_id": str(ticket.id),
        "opened_at": ticket.created_at.isoformat() if ticket.created_at else None,
        "last_message_excerpt": (ticket.reason or "")[:200],
        "status": ticket.status,
        "assignee_id": ticket.assigned_to,
        "assignee_name": assignee_name,
    }
