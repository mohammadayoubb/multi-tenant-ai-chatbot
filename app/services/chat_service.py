# Owner: Nasser
"""Chat orchestration service.

This service connects router, agent, RAG, memory, and guardrails.

The service is the main Owner B entry point:
- append redacted visitor message to Redis memory
- classify the message with the router
- execute a cheap workflow path or the bounded agent
- append redacted assistant answer to Redis memory
- return the final chat response
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.agent import run_agent
from app.agent.router import RouteDecision, route_message_decision
from app.agent.tools import capture_lead, escalate, extract_lead_fields, rag_search
from app.domain.chat import ChatResponse
from app.infra.cache import MemoryMessage, SessionMemory
from app.infra.redaction import redact_text


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

    async def handle_message(self, tenant_id: int, message: str, session_id: str) -> ChatResponse:
        """Route a message through the workflow path or bounded agent path.

        tenant_id must come from trusted backend context, usually the verified
        widget token. The visitor and LLM must never choose the tenant.
        """

        redacted_message = redact_text(message)
        await self._memory.append_message(
            tenant_id=tenant_id,
            session_id=session_id,
            role="user",
            content=redacted_message,
        )

        recent_memory = await self._memory.get_messages(
            tenant_id=tenant_id,
            session_id=session_id,
        )

        decision = await route_message_decision(message)
        turn_result = await self._execute_decision(
            tenant_id=tenant_id,
            session_id=session_id,
            message=message,
            decision=decision,
            recent_memory=recent_memory,
        )

        await self._memory.append_message(
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
        tenant_id: int,
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
                name=name,
                contact=contact,
                intent=message,
                session=self._session,
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
        )

        return _TurnResult(
            answer=agent_result.answer,
            route=agent_result.route,
            used_tools=agent_result.used_tools,
        )