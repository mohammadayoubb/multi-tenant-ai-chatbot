# Owner: Nasser
"""Integration test for Redis fail-soft (SC-013, task T062a).

When the Redis-backed session memory becomes unavailable mid-session, the
chat path must:

1. Continue to produce HTTP 200 / a coherent answer (the visitor never sees
   an error).
2. Emit exactly one ``memory.unavailable`` audit row per (tenant, session)
   even if multiple operations failed (de-dup tracker resets only on
   process restart — contract C-T2-7).
3. Keep responding without memory for the rest of the session.

This stays in-process: a stub SessionMemory raises ``MemoryUnavailableError``
to simulate the dropped Redis connection. A fake TenantRepository captures
the audit emissions so we can count them.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import pytest

import app.services.chat_service as chat_service_module
from app.agent.router import RouteDecision
from app.infra.cache import MemoryMessage, MemoryUnavailableError
from app.services.chat_service import (
    ChatService,
    reset_memory_unavailable_tracker_for_tests,
)


# ---------------------------------------------------------------------------
# Stubs
# ---------------------------------------------------------------------------


class _UnavailableSessionMemory:
    """Mimics SessionMemory after Redis dropped — every op raises."""

    async def append_message(self, *, tenant_id, session_id, role, content) -> None:  # noqa: ARG002
        raise MemoryUnavailableError("redis went away")

    async def get_messages(self, *, tenant_id, session_id):  # noqa: ARG002
        raise MemoryUnavailableError("redis went away")


class _ToggleSessionMemory:
    """First N operations succeed (warm Redis), then drop to unavailable."""

    def __init__(self, healthy_ops: int) -> None:
        self._remaining = healthy_ops
        self.appended: list[dict[str, Any]] = []

    async def append_message(self, *, tenant_id, session_id, role, content) -> None:
        if self._remaining <= 0:
            raise MemoryUnavailableError("redis went away")
        self._remaining -= 1
        self.appended.append(
            {
                "tenant_id": tenant_id,
                "session_id": session_id,
                "role": role,
                "content": content,
            }
        )

    async def get_messages(self, *, tenant_id, session_id):  # noqa: ARG002
        if self._remaining <= 0:
            raise MemoryUnavailableError("redis went away")
        self._remaining -= 1
        return [MemoryMessage(role="user", content="prior turn", created_at="now")]


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


@pytest.fixture(autouse=True)
def _reset_memory_tracker() -> None:
    reset_memory_unavailable_tracker_for_tests()


@pytest.fixture
def patched_chat(monkeypatch: pytest.MonkeyPatch) -> _AuditCollector:
    """Stub the router → workflow (cheap path) and the TenantRepository emit hook."""

    async def _fake_route(_message: str) -> RouteDecision:
        return RouteDecision(
            route="rag_search",
            label="faq",
            confidence=0.95,
            reason="High-confidence FAQ.",
            source="fallback_rules",
        )

    monkeypatch.setattr(chat_service_module, "route_message_decision", _fake_route)

    async def _fake_rag_search(**kwargs: Any) -> dict[str, Any]:  # noqa: ARG001
        return {
            "status": "ok",
            "answer": "Stubbed answer that should still reach the visitor.",
            "chunks": [],
        }

    monkeypatch.setattr(chat_service_module, "rag_search", _fake_rag_search)

    collector = _AuditCollector()
    monkeypatch.setattr(chat_service_module, "TenantRepository", collector.make_repo)
    return collector


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_chat_continues_when_memory_drops_mid_session(
    patched_chat: _AuditCollector,
) -> None:
    """Healthy Redis turn → Redis drops → next turn returns 200-equivalent."""
    fake_session = object()
    memory = _ToggleSessionMemory(healthy_ops=2)  # append + get succeed once
    service = ChatService(session=fake_session, memory=memory)  # type: ignore[arg-type]
    tenant_id = uuid4()
    session_id = "redis-fallback-session"

    # First turn — Redis healthy. Append succeeds; get succeeds.
    first = await service.handle_message(
        tenant_id=tenant_id,
        message="warm-up message",
        session_id=session_id,
    )
    # The second append (assistant reply) raised — that is the first failure.
    assert "Stubbed answer" in first.answer
    audits_after_first = [e for e in patched_chat.events if e["action"] == "memory.unavailable"]
    assert len(audits_after_first) == 1

    # Second turn — Redis stays down. The visitor still gets an answer.
    second = await service.handle_message(
        tenant_id=tenant_id,
        message="follow-up after redis dropped",
        session_id=session_id,
    )
    assert "Stubbed answer" in second.answer

    # Only ONE audit row per (tenant, session) even though multiple ops failed.
    audits_after_second = [e for e in patched_chat.events if e["action"] == "memory.unavailable"]
    assert len(audits_after_second) == 1
    assert audits_after_second[0]["metadata"]["session_id"] == session_id


@pytest.mark.asyncio
async def test_chat_succeeds_when_memory_is_unavailable_from_first_op(
    patched_chat: _AuditCollector,
) -> None:
    """Cold Redis (down from the start) — chat still returns a coherent answer."""
    fake_session = object()
    service = ChatService(session=fake_session, memory=_UnavailableSessionMemory())  # type: ignore[arg-type]
    response = await service.handle_message(
        tenant_id=uuid4(),
        message="anything",
        session_id="cold-redis",
    )
    assert "Stubbed answer" in response.answer
    audits = [e for e in patched_chat.events if e["action"] == "memory.unavailable"]
    assert len(audits) == 1


@pytest.mark.asyncio
async def test_distinct_sessions_each_audit_once_under_memory_outage(
    patched_chat: _AuditCollector,
) -> None:
    """The dedup is per (tenant, session) — a second session must still
    emit its own ``memory.unavailable`` row."""
    fake_session = object()
    tenant_id = uuid4()

    for session_id in ("multi-A", "multi-B"):
        service = ChatService(
            session=fake_session,
            memory=_UnavailableSessionMemory(),  # type: ignore[arg-type]
        )
        await service.handle_message(
            tenant_id=tenant_id,
            message="hi",
            session_id=session_id,
        )

    audits = [e for e in patched_chat.events if e["action"] == "memory.unavailable"]
    assert len(audits) == 2
    assert {e["metadata"]["session_id"] for e in audits} == {"multi-A", "multi-B"}


@pytest.mark.asyncio
async def test_no_audit_emitted_without_db_session(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """If the ChatService was constructed without a DB session, the
    memory-unavailable signal is silent — there's nowhere to write the audit."""
    audit_events: list[dict[str, Any]] = []

    class _CollectingRepo:
        def __init__(self, session: Any) -> None:
            pass

        async def add_audit_log(self_inner, **kwargs):  # noqa: ANN001, ANN003
            audit_events.append(kwargs)

    async def _fake_route(_message: str) -> RouteDecision:
        return RouteDecision(
            route="rag_search",
            label="faq",
            confidence=0.95,
            reason="ok",
            source="fallback_rules",
        )

    async def _fake_rag_search(**kwargs: Any) -> dict[str, Any]:  # noqa: ARG001
        return {"status": "ok", "answer": "ok", "chunks": []}

    monkeypatch.setattr(chat_service_module, "route_message_decision", _fake_route)
    monkeypatch.setattr(chat_service_module, "rag_search", _fake_rag_search)
    monkeypatch.setattr(chat_service_module, "TenantRepository", _CollectingRepo)

    service = ChatService(session=None, memory=_UnavailableSessionMemory())  # type: ignore[arg-type]
    await service.handle_message(
        tenant_id=uuid4(),
        message="anything",
        session_id="no-db-session",
    )
    # Without a DB session there is no place to write the audit, so the
    # collector stays empty even though Redis was unavailable.
    assert audit_events == []
