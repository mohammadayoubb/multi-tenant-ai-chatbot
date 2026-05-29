# Owner: Nasser
"""Chat orchestration service.

This service connects router, agent, RAG, memory, and guardrails.

The service is the main Owner B entry point:
- append redacted visitor message to Redis memory
- classify the message with the router
- execute a cheap workflow path or the bounded agent
- append redacted assistant answer to Redis memory
- return the final chat response

Per FR-029 / task T060: when Redis-backed session memory is unreachable the
service continues without memory (fail-soft) and emits a one-shot
``memory.unavailable`` audit per (tenant, session) so the operator can see
how often the fallback path fires.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import run_agent
from app.agent.router import RouteDecision, route_message_decision
from app.agent.tools import capture_lead, escalate, extract_lead_fields, rag_search
from app.domain.chat import ChatResponse
from app.infra.cache import MemoryMessage, MemoryUnavailableError, SessionMemory
from app.infra.redaction import redact_text
from app.repositories.tenant_repo import TenantRepository

_log = logging.getLogger(__name__)

# Per-process set of (tenant_id, session_id) keys that have already received
# a memory.unavailable audit. Resets on process restart (per C-T2-7).
_SEEN_MEMORY_UNAVAILABLE_KEYS: set[tuple[str, str]] = set()


@dataclass(frozen=True)
class _TurnResult:
    """Internal result after executing one router decision."""

    answer: str
    route: str
    used_tools: list[str] = field(default_factory=list)


class ChatService:
    """Handle one visitor chat turn."""

    def __init__(
        self,
        session: AsyncSession | None = None,
        memory: SessionMemory | None = None,
    ) -> None:
        self._session = session
        self._memory = memory or SessionMemory()

    async def handle_message(self, tenant_id: UUID, message: str, session_id: str) -> ChatResponse:
        """Route a message through the workflow path or bounded agent path.

        tenant_id must come from trusted backend context, usually the verified
        widget token. The visitor and LLM must never choose the tenant.
        """
        redacted_message = redact_text(message)
        await self._safe_append_memory(
            tenant_id=tenant_id,
            session_id=session_id,
            role="user",
            content=redacted_message,
        )

        recent_memory = await self._safe_get_memory(
            tenant_id=tenant_id, session_id=session_id
        )

        decision = await route_message_decision(message)
        turn_result = await self._execute_decision(
            tenant_id=tenant_id,
            session_id=session_id,
            message=message,
            decision=decision,
            recent_memory=recent_memory,
        )

        await self._safe_append_memory(
            tenant_id=tenant_id,
            session_id=session_id,
            role="assistant",
            content=redact_text(turn_result.answer),
        )

        return ChatResponse(
            answer=turn_result.answer,
            route=turn_result.route,
            used_tools=turn_result.used_tools,
        )

    async def _execute_decision(
        self,
        tenant_id: UUID,
        session_id: str,
        message: str,
        decision: RouteDecision,
        recent_memory: list[MemoryMessage],
    ) -> _TurnResult:
        """Execute the workflow or agent path selected by the router."""

        if decision.route == "blocked":
            return _TurnResult(
                answer="I can’t help with that request.",
                route="blocked",
                used_tools=[],
            )

        if decision.route == "rag_search":
            result = await rag_search(
                tenant_id=tenant_id,
                query=message,
                top_k=5,
                session=self._session,
            )
            return _TurnResult(
                answer=str(result["answer"]),
                route="workflow",
                used_tools=["rag_search"],
            )

        if decision.route == "capture_lead":
            name, contact = extract_lead_fields(message)
            result = await capture_lead(
                tenant_id=tenant_id,
                session_id=session_id,
                name=name,
                contact=contact,
                intent=message,
                session=self._session,
            )

            if result.get("status") == "rate_limited":
                return _TurnResult(
                    answer=(
                        "I've already captured your details — the team will reach out shortly."
                    ),
                    route="workflow",
                    used_tools=["capture_lead"],
                )

            if contact is None:
                answer = (
                    "I can pass this to the team. Please share an email or phone number "
                    "so they can contact you."
                )
            else:
                answer = f"Thanks — I captured your request. Lead status: {result['status']}."

            return _TurnResult(
                answer=answer,
                route="workflow",
                used_tools=["capture_lead"],
            )

        if decision.route == "escalate":
            result = await escalate(
                tenant_id=tenant_id,
                conversation_id=session_id,
                reason=decision.reason,
                session=self._session,
            )

            used_tools = ["escalate"] if result["status"] == "escalated" else []
            return _TurnResult(
                answer="I escalated this conversation to a human so the team can follow up.",
                route="escalate",
                used_tools=used_tools,
            )

        agent_result = await run_agent(
            tenant_id=tenant_id,
            message=message,
            session_id=session_id,
            memory=recent_memory,
            session=self._session,
            route_reason=decision.reason,
        )

        return _TurnResult(
            answer=agent_result.answer,
            route=agent_result.route,
            used_tools=agent_result.used_tools,
        )

    # ----- memory fail-soft helpers (T060) -----

    async def _safe_append_memory(
        self,
        *,
        tenant_id: Any,
        session_id: str,
        role: str,
        content: str,
    ) -> None:
        try:
            await self._memory.append_message(
                tenant_id=tenant_id,
                session_id=session_id,
                role=role,
                content=content,
            )
        except MemoryUnavailableError:
            await self._record_memory_unavailable(tenant_id, session_id)

    async def _safe_get_memory(
        self, *, tenant_id: Any, session_id: str
    ) -> list[MemoryMessage]:
        try:
            return await self._memory.get_messages(
                tenant_id=tenant_id, session_id=session_id
            )
        except MemoryUnavailableError:
            await self._record_memory_unavailable(tenant_id, session_id)
            return []

    async def _record_memory_unavailable(
        self, tenant_id: Any, session_id: str
    ) -> None:
        key = (str(tenant_id), session_id)
        if key in _SEEN_MEMORY_UNAVAILABLE_KEYS:
            return
        _SEEN_MEMORY_UNAVAILABLE_KEYS.add(key)
        if self._session is None:
            return
        try:
            repo = TenantRepository(self._session)
            await repo.add_audit_log(
                tenant_id=_coerce_uuid(tenant_id),
                actor_id=None,
                actor_role="agent",
                action="memory.unavailable",
                metadata={"session_id": session_id},
            )
        except Exception:  # pragma: no cover - defensive
            _log.warning(
                "memory.unavailable audit emission failed", exc_info=True
            )


def _coerce_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


def reset_memory_unavailable_tracker_for_tests() -> None:
    """Clear the per-process dedup set (tests only)."""
    _SEEN_MEMORY_UNAVAILABLE_KEYS.clear()
