# Owner: Nasser
"""Bounded tool-calling agent.

The router handles easy messages first. Only ambiguous or multi-step messages
reach this agent.

The agent is bounded by:
- a max iteration count
- a per-turn token budget
- a strict tool allowlist
- tenant_id passed only from trusted backend context
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import capture_lead, escalate, extract_lead_fields, rag_search
from app.infra.cache import MemoryMessage

MAX_AGENT_ITERATIONS = 5
MAX_AGENT_TOKENS_PER_TURN = 4000

ToolName = Literal["rag_search", "capture_lead", "escalate"]
ALLOWED_TOOLS: set[ToolName] = {"rag_search", "capture_lead", "escalate"}


@dataclass
class AgentResult:
    """Result returned by the bounded agent path."""

    answer: str
    used_tools: list[str] = field(default_factory=list)
    route: str = "agent"
    citations: list[dict[str, object]] = field(default_factory=list)
    escalated: bool = False


@dataclass(frozen=True)
class _AgentPlan:
    """Lightweight deterministic plan until hosted LLM tool-calling is wired."""

    tools: list[ToolName]
    reason: str


async def run_agent(
    tenant_id: UUID,
    message: str,
    session_id: str,
    memory: list[MemoryMessage] | None = None,
    session: AsyncSession | None = None,
) -> AgentResult:
    """Run the bounded agent path.

    tenant_id must come from the verified widget/backend context. The model,
    visitor, or message text never decides the tenant.
    """

    cleaned_message = message.strip()
    if not cleaned_message:
        result = await _call_tool(
            tool_name="escalate",
            tenant_id=tenant_id,
            session_id=session_id,
            message=message,
            session=session,
            reason="Empty message reached agent path.",
        )
        return AgentResult(
            answer="I could not process an empty message, so I escalated this conversation.",
            used_tools=["escalate"],
            escalated=result.get("status") == "escalated",
        )

    budget_used = _rough_token_count(cleaned_message) + _memory_token_count(memory)
    remaining_budget = MAX_AGENT_TOKENS_PER_TURN - budget_used

    if remaining_budget <= 0:
        result = await _call_tool(
            tool_name="escalate",
            tenant_id=tenant_id,
            session_id=session_id,
            message=message,
            session=session,
            reason="Visitor turn exceeded the agent token budget.",
        )
        return AgentResult(
            answer="This message is too large for one turn, so I escalated it to a human.",
            used_tools=["escalate"],
            escalated=result.get("status") == "escalated",
        )

    plan = _plan_tools(cleaned_message)

    used_tools: list[str] = []
    citations: list[dict[str, object]] = []
    answer_parts: list[str] = []
    escalated = False

    for iteration, tool_name in enumerate(plan.tools, start=1):
        if iteration > MAX_AGENT_ITERATIONS:
            break

        if tool_name not in ALLOWED_TOOLS:
            result = await _call_tool(
                tool_name="escalate",
                tenant_id=tenant_id,
                session_id=session_id,
                message=message,
                session=session,
                reason=f"Agent attempted disallowed tool: {tool_name}",
            )
            return AgentResult(
                answer="I could not complete this safely, so I escalated it to a human.",
                used_tools=[*used_tools, "escalate"],
                citations=citations,
                escalated=result.get("status") == "escalated",
            )

        result = await _call_tool(
            tool_name=tool_name,
            tenant_id=tenant_id,
            session_id=session_id,
            message=cleaned_message,
            session=session,
            reason=plan.reason,
        )

        used_tools.append(tool_name)

        if tool_name == "rag_search":
            answer_parts.append(str(result.get("answer", "")))
            raw_chunks = result.get("chunks", [])
            if isinstance(raw_chunks, list):
                citations.extend(chunk for chunk in raw_chunks if isinstance(chunk, dict))

        elif tool_name == "capture_lead":
            if result.get("has_contact") is False:
                answer_parts.append(
                    "I can help arrange follow-up. Please share an email or phone number "
                    "so the team can contact you."
                )
            else:
                answer_parts.append(
                    f"I captured this as a follow-up request. Lead status: {result.get('status', 'captured')}."
                )

        elif tool_name == "escalate":
            escalated = result.get("status") == "escalated"
            answer_parts.append("I escalated this conversation to a human so the team can follow up.")
            break

    if not answer_parts:
        result = await _call_tool(
            tool_name="escalate",
            tenant_id=tenant_id,
            session_id=session_id,
            message=message,
            session=session,
            reason="Agent produced no answer within allowed tool plan.",
        )
        return AgentResult(
            answer="I could not resolve this safely, so I escalated it.",
            used_tools=[*used_tools, "escalate"],
            citations=citations,
            escalated=result.get("status") == "escalated",
        )

    return AgentResult(
        answer="\n\n".join(part for part in answer_parts if part.strip()),
        used_tools=used_tools,
        citations=citations,
        escalated=escalated,
    )


def _plan_tools(message: str) -> _AgentPlan:
    """Choose a bounded tool plan.

    This is a deterministic stand-in for hosted LLM tool-calling. It still
    demonstrates the production pattern: the agent selects from a strict tool
    allowlist and may use multiple tools for one hard turn.
    """

    lowered = message.lower()

    if _needs_human(lowered):
        return _AgentPlan(
            tools=["escalate"],
            reason="Visitor explicitly requested human help or the request is out of scope.",
        )

    needs_lead = _needs_lead_capture(lowered)
    needs_knowledge = _needs_knowledge_lookup(lowered)

    if needs_knowledge and needs_lead:
        return _AgentPlan(
            tools=["rag_search", "capture_lead"],
            reason="Visitor asked for information and also showed follow-up/sales intent.",
        )

    if needs_lead:
        return _AgentPlan(
            tools=["capture_lead"],
            reason="Visitor showed follow-up or sales intent.",
        )

    return _AgentPlan(
        tools=["rag_search"],
        reason="Visitor asked for tenant knowledge.",
    )


async def _call_tool(
    tool_name: ToolName,
    tenant_id: UUID,
    session_id: str,
    message: str,
    session: AsyncSession | None,
    reason: str,
) -> dict[str, Any]:
    """Call one allowed tool with tenant-scoped arguments."""

    if tool_name not in ALLOWED_TOOLS:
        raise ValueError(f"Disallowed tool requested: {tool_name}")

    if tool_name == "rag_search":
        return await rag_search(
            tenant_id=tenant_id,
            query=message,
            top_k=5,
            session=session,
        )

    if tool_name == "capture_lead":
        name, contact = extract_lead_fields(message)
        return await capture_lead(
            tenant_id=tenant_id,
            name=name,
            contact=contact,
            intent=message,
            session=session,
        )

    return await escalate(
        tenant_id=tenant_id,
        conversation_id=session_id,
        reason=reason,
    )


def _needs_human(lowered_message: str) -> bool:
    """Detect explicit human handoff requests."""

    return any(
        term in lowered_message
        for term in (
            "human",
            "real person",
            "live person",
            "representative",
            "manager",
            "support team",
            "talk to someone",
            "speak to someone",
            "live agent",
        )
    )


def _needs_lead_capture(lowered_message: str) -> bool:
    """Detect follow-up/sales/contact intent."""

    return any(
        term in lowered_message
        for term in (
            "contact",
            "call me",
            "email me",
            "quote",
            "pricing",
            "demo",
            "sales",
            "book a meeting",
        )
    )


def _needs_knowledge_lookup(lowered_message: str) -> bool:
    """Detect whether the visitor is asking for tenant knowledge."""

    question_terms = (
        "what",
        "how",
        "when",
        "where",
        "why",
        "which",
        "do you",
        "can you",
        "?",
    )
    knowledge_terms = (
        "plan",
        "service",
        "services",
        "offer",
        "offers",
        "include",
        "included",
        "pricing options",
        "location",
        "located",
    )

    return any(term in lowered_message for term in question_terms) or any(
        term in lowered_message for term in knowledge_terms
    )


def _rough_token_count(text: str) -> int:
    """Approximate tokens without importing tokenizer dependencies."""

    return max(1, len(text.split()))


def _memory_token_count(memory: list[MemoryMessage] | None) -> int:
    """Approximate memory token usage for the per-turn budget."""

    if not memory:
        return 0

    return sum(_rough_token_count(item.content) for item in memory[-6:])
