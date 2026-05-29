# Owner: Nasser
"""Schemas for the escalations list + patch endpoints (T026).

Shapes consumed by ``GET /escalations`` and ``PATCH /escalations/{id}``.
The route layer currently emits/accepts plain ``dict``; these schemas are the
authoritative request/response contract referenced by the admin UI
(`admin/escalations_page.py`) and the integration tests in
``tests/integration/test_escalations_endpoint.py``.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EscalationListItem(BaseModel):
    """One row of ``GET /escalations``.

    ``last_message_excerpt`` is sourced from the redacted ``reason`` field on
    ``escalation_tickets`` (Principle V — already redacted at INSERT time by
    ``EscalationRepository.create``).
    """

    model_config = ConfigDict(extra="forbid")

    ticket_id: str
    opened_at: str | None
    last_message_excerpt: str
    status: str
    assignee_id: str | None = None
    assignee_name: str | None = None


class EscalationPatchRequest(BaseModel):
    """Body for ``PATCH /escalations/{id}``.

    ``tenant_id`` / ``actor_id`` / ``role`` are intentionally absent — they
    derive from the admin JWT in the route layer. ``extra=forbid`` rejects any
    smuggled identity field with 422.
    """

    model_config = ConfigDict(extra="forbid")

    status: str | None = Field(
        default=None, pattern="^(pending|in_progress|resolved|open)$"
    )
    assignee_id: str | None = None
