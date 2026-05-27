# Owner: Nasser
"""Bounded tool-calling agent.

The agent must have a max iteration and token budget. This implementation keeps
an explicit allowlist of the three project tools and uses lightweight planning
rules until the hosted LLM adapter is connected.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import capture_lead, escalate, extract_lead_fields, rag_search
from app.infra.cache import MemoryMessage

MAX_AGENT_ITERATIONS = 5
MAX_AGENT_TOKENS_PER_TURN = 4000
ALLOWED_TOOLS = {"rag_search", "capture_lead", "escalate"}


@dataclass
class AgentResult:
    """Result returned by the bounded agent path."""

    answer: str
    used_tools: list[str] = field(default_factory=list)
    route: str = "agent"
    citations: list[dict[str, object]] = field(default_factory=list)
    escalated: bool = False


async def run_agent(
    tenant_id: int,
    message: str,
    session_id: str,
    memory: list[MemoryMessage] | None = None,
    session: AsyncSession | None = None,
) -> AgentResult:
    """Run the bounded agent path.

    The model/visitor never supplies trusted tenant_id. The service layer passes
    tenant_id from the verified widget token.
    """

    del memory  # reserved for hosted LLM prompt context once the adapter is wired

    remaining_budget = MAX_AGENT_TOKENS_PER_TURN - _rough_token_count(message)
    if remaining_budget <= 0:
        escalation = await escalate(
            tenant_id=tenant_id,
            conversation_id=session_id,
            reason="Visitor message exceeded per-turn token budget.",
        )
        return AgentResult(
            answer="This message is too large for one turn, so I escalated it to a human.",
            used_tools=["escalate"],
            escalated=True,
            citations=[],
        )

    lowered = message.lower()
    used_tools: list[str] = []
    citations: list[dict[str, object]] = []

    for iteration in range(MAX_AGENT_ITERATIONS):
        if iteration == 0 and _needs_human(lowered):
            result = await escalate(
                tenant_id=tenant_id,
                conversation_id=session_id,
                reason="Visitor explicitly requested a human or the request is out of scope.",
            )
            used_tools.append("escalate")
            return AgentResult(
                answer="I escalated this conversation to a human so the team can follow up.",
                used_tools=used_tools,
                citations=citations,
                escalated=result["status"] == "escalated",
            )

        if iteration == 0 and _needs_lead_capture(lowered):
            name, contact = extract_lead_fields(message)
            result = await capture_lead(
                tenant_id=tenant_id,
                name=name,
                contact=contact,
                intent=message,
                session=session,
            )
            used_tools.append("capture_lead")
            if contact is None:
                return AgentResult(
                    answer=(
                        "I can help arrange follow-up. Please share an email or phone number "
                        "so the team can contact you."
                    ),
                    used_tools=used_tools,
                    citations=citations,
                )
            return AgentResult(
                answer=f"Thanks — I captured your request for follow-up. Lead status: {result['status']}.",
                used_tools=used_tools,
                citations=citations,
            )

        rag_result = await rag_search(
            tenant_id=tenant_id,
            query=message,
            top_k=5,
            session=session,
        )
        used_tools.append("rag_search")
        chunks = list(rag_result.get("chunks", []))
        citations = [chunk for chunk in chunks if isinstance(chunk, dict)]
        answer = str(rag_result["answer"])

        if _needs_lead_capture(lowered):
            name, contact = extract_lead_fields(message)
            await capture_lead(
                tenant_id=tenant_id,
                name=name,
                contact=contact,
                intent=message,
                session=session,
            )
            used_tools.append("capture_lead")
            answer = f"{answer}\n\nI also captured this as a follow-up request for the tenant team."

        return AgentResult(
            answer=answer,
            used_tools=used_tools,
            citations=citations,
        )

    escalation = await escalate(
        tenant_id=tenant_id,
        conversation_id=session_id,
        reason="Agent reached maximum tool-call iterations.",
    )
    return AgentResult(
        answer="I could not resolve this safely in the allowed tool budget, so I escalated it.",
        used_tools=[*used_tools, "escalate"],
        citations=citations,
        escalated=escalation["status"] == "escalated",
    )


def _needs_human(lowered_message: str) -> bool:
    return any(
        term in lowered_message
        for term in ("human", "person", "representative", "manager", "support team")
    )


def _needs_lead_capture(lowered_message: str) -> bool:
    return any(
        term in lowered_message
        for term in ("contact", "call me", "email me", "quote", "pricing", "demo", "sales")
    )


def _rough_token_count(text: str) -> int:
    """Approximate tokens without importing tokenizer dependencies."""

    return max(1, len(text.split()))
