# Owner: Nasser
"""Integration test for ``escalate`` real-INSERT + per-session dedup (task T056).

Covers contract C-T2-5:
- First call within a session INSERTs an EscalationTicket and emits
  ``escalation.created`` audit (with a redacted reason_excerpt).
- Subsequent calls within the same session return the same ticket_id
  without a second INSERT (1-per-session rule).
- After insert the ticket is observable through the "list by tenant" path
  that the GET /escalations route uses.

In-process — the EscalationRepository, Conversation lookup, and
TenantRepository seams are monkey-patched. The dedup invariant under test
lives entirely in `app/agent/tools.py::escalate`.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import UUID, uuid4

import pytest

import app.agent.tools as tools_module
from app.agent.tools import escalate


@dataclass
class _FakeTicket:
    id: UUID = field(default_factory=uuid4)
    tenant_id: UUID | None = None
    conversation_id: UUID | None = None
    reason: str = ""
    status: str = "open"


class _FakeEscalationRepoFactory:
    """One backing store; new repo wrappers all see the same rows."""

    def __init__(self) -> None:
        self.rows: list[_FakeTicket] = []
        self.create_call_count = 0

    def __call__(self, session: Any):  # noqa: ARG002 — match real signature
        store = self

        class _FakeEscalationRepo:
            async def create(
                self_inner,
                *,
                tenant_id,
                conversation_id,
                reason,
                last_message_excerpt="",
            ) -> _FakeTicket:
                store.create_call_count += 1
                ticket = _FakeTicket(
                    tenant_id=tenant_id,
                    conversation_id=conversation_id,
                    reason=reason,
                )
                store.rows.append(ticket)
                return ticket

            async def list_by_tenant(self_inner, tenant_id: UUID) -> list[_FakeTicket]:
                return [r for r in store.rows if r.tenant_id == tenant_id]

        return _FakeEscalationRepo()


class _AuditCollector:
    def __init__(self) -> None:
        self.events: list[dict[str, Any]] = []

    def make_repo(self, session: Any):  # noqa: ARG002
        collector = self

        class _FakeTenantRepo:
            async def add_audit_log(
                self_inner,
                *,
                tenant_id,
                actor_id,
                actor_role,
                action,
                metadata,
            ) -> None:
                collector.events.append(
                    {
                        "tenant_id": tenant_id,
                        "actor_id": actor_id,
                        "actor_role": actor_role,
                        "action": action,
                        "metadata": metadata,
                    }
                )

        return _FakeTenantRepo()


@dataclass
class _FakeConversation:
    id: UUID
    tenant_id: UUID
    session_id: str


@pytest.fixture
def patched_escalate(monkeypatch: pytest.MonkeyPatch):
    """Patch escalate's DB seams; return spies for assertion."""
    repo_factory = _FakeEscalationRepoFactory()
    audits = _AuditCollector()

    conversations: dict[tuple[UUID, str], _FakeConversation] = {}

    async def _fake_ensure_conversation(session, tenant_id, session_id):  # noqa: ARG001
        tid = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
        key = (tid, session_id)
        if key in conversations:
            return conversations[key]
        conv = _FakeConversation(id=uuid4(), tenant_id=tid, session_id=session_id)
        conversations[key] = conv
        return conv

    async def _fake_find_existing(session, tenant_id, conversation_id):  # noqa: ARG001
        tid = tenant_id if isinstance(tenant_id, UUID) else UUID(str(tenant_id))
        for row in repo_factory.rows:
            if row.tenant_id == tid and row.conversation_id == conversation_id:
                return row
        return None

    monkeypatch.setattr(tools_module, "EscalationRepository", repo_factory)
    monkeypatch.setattr(tools_module, "TenantRepository", audits.make_repo)
    monkeypatch.setattr(tools_module, "_ensure_conversation", _fake_ensure_conversation)
    monkeypatch.setattr(tools_module, "_find_existing_escalation", _fake_find_existing)

    return repo_factory, audits


@pytest.mark.asyncio
async def test_first_call_inserts_and_emits_audit(patched_escalate) -> None:
    repo_factory, audits = patched_escalate
    tenant_id = uuid4()
    session_id = "session-escalate-1"
    fake_session = object()

    result = await escalate(
        tenant_id=tenant_id,
        conversation_id=session_id,
        reason="Visitor explicitly asked for a human.",
        session=fake_session,
    )

    assert result["status"] == "escalated"
    assert "deduplicated" not in result
    assert repo_factory.create_call_count == 1
    assert len(repo_factory.rows) == 1
    assert repo_factory.rows[0].tenant_id == tenant_id

    created_audits = [e for e in audits.events if e["action"] == "escalation.created"]
    assert len(created_audits) == 1
    metadata = created_audits[0]["metadata"]
    assert metadata["ticket_id"] == result["ticket_id"]
    assert metadata["session_id"] == session_id
    # reason_excerpt MUST be present (Principle V — redacted-only persistence).
    assert "reason_excerpt" in metadata
    assert len(metadata["reason_excerpt"]) <= 80


@pytest.mark.asyncio
async def test_second_call_in_same_session_returns_existing_without_insert(
    patched_escalate,
) -> None:
    repo_factory, audits = patched_escalate
    tenant_id = uuid4()
    session_id = "session-escalate-2"
    fake_session = object()

    first = await escalate(
        tenant_id=tenant_id,
        conversation_id=session_id,
        reason="First escalation.",
        session=fake_session,
    )
    second = await escalate(
        tenant_id=tenant_id,
        conversation_id=session_id,
        reason="Second attempt — same session.",
        session=fake_session,
    )

    assert first["status"] == "escalated"
    assert second["status"] == "escalated"
    assert second["ticket_id"] == first["ticket_id"]
    assert second.get("deduplicated") is True

    # Exactly one INSERT, regardless of how many times the agent invoked escalate.
    assert repo_factory.create_call_count == 1
    assert len(repo_factory.rows) == 1

    # Exactly one audit row — the second call must NOT re-emit escalation.created.
    created_audits = [e for e in audits.events if e["action"] == "escalation.created"]
    assert len(created_audits) == 1


@pytest.mark.asyncio
async def test_ticket_visible_via_list_by_tenant(patched_escalate) -> None:
    """The dedup'd ticket appears in EscalationRepository.list_by_tenant — the
    same call path that backs GET /escalations (US1 #5)."""
    repo_factory, _audits = patched_escalate
    tenant_id = uuid4()
    fake_session = object()

    result = await escalate(
        tenant_id=tenant_id,
        conversation_id="session-list-check",
        reason="Visible to TA via Escalations tab.",
        session=fake_session,
    )

    # The route handler builds an EscalationRepository from the request session
    # and calls list_by_tenant — exercise the same surface.
    repo = repo_factory(fake_session)
    rows = await repo.list_by_tenant(tenant_id)
    assert len(rows) == 1
    assert str(rows[0].id) == result["ticket_id"]
    assert rows[0].tenant_id == tenant_id


@pytest.mark.asyncio
async def test_distinct_sessions_each_get_their_own_ticket(patched_escalate) -> None:
    repo_factory, audits = patched_escalate
    tenant_id = uuid4()
    fake_session = object()

    a = await escalate(
        tenant_id=tenant_id,
        conversation_id="sess-multi-A",
        reason="A",
        session=fake_session,
    )
    b = await escalate(
        tenant_id=tenant_id,
        conversation_id="sess-multi-B",
        reason="B",
        session=fake_session,
    )

    assert a["ticket_id"] != b["ticket_id"]
    assert repo_factory.create_call_count == 2
    created_audits = [e for e in audits.events if e["action"] == "escalation.created"]
    assert len(created_audits) == 2


@pytest.mark.asyncio
async def test_escalate_without_session_returns_synthetic_ticket(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No DB session ⇒ synthetic ticket_id, no INSERT path exercised."""
    repo_factory = _FakeEscalationRepoFactory()
    monkeypatch.setattr(tools_module, "EscalationRepository", repo_factory)

    result = await escalate(
        tenant_id=uuid4(),
        conversation_id="sess-no-db",
        reason="dev mode",
        session=None,
    )

    assert result["status"] == "escalated"
    assert UUID(result["ticket_id"])  # parseable UUID
    assert repo_factory.create_call_count == 0
