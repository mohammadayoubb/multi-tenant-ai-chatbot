# Owner: Nasser
"""Bounded tool-calling agent (Phase B'3, T058 / T059).

The router handles easy messages first. Only ambiguous, low-confidence, or
multi-step messages reach this agent.

The loop is bounded by:
- ``MAX_AGENT_ITERATIONS = 5``     — hard cap on iterations per turn
- ``MAX_AGENT_TOKENS_PER_TURN``    — hard cap on cumulative tokens per turn
- the strict 3-tool allowlist (rag_search / capture_lead / escalate)
- ``tenant_id`` passed only from trusted backend context

DECISION 19b (revised): the LLM is Groq ``llama-3.3-70b-versatile`` via the
``groq`` SDK. When no Groq client can be constructed (no API key / SDK
missing), the loop falls back to a deterministic plan so local tests and
dev environments still produce a coherent answer.

Per contract C-T2-3:
- ``agent.turn_started`` emitted on entry (metadata: session_id, route_reason).
- ``agent.tool_called`` emitted per tool execution (metadata: tool_name, iteration).
- ``agent.turn_completed`` emitted on normal exit.
- On cap-hit (iteration OR token), ``escalate(reason="agent_cap_hit")`` is
  invoked exactly once, the safe-default message is returned, and
  ``agent.iteration_cap_hit`` / ``agent.token_cap_hit`` is emitted.
- ``capture_lead`` is NEVER called on the cap-hit path.

Per Principle V (T059): any ``route_reason`` that could carry visitor-
supplied text is redacted before being persisted in audit metadata.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal
from uuid import UUID

from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.agent.tools import (
    CaptureLeadArgs,
    EscalateArgs,
    RagSearchArgs,
    capture_lead,
    escalate,
    extract_lead_fields,
    rag_search,
)
from app.infra.cache import MemoryMessage
from app.infra.llm import GroqAgentClient, try_build_default_groq_client
from app.infra.redaction import redact_text
from app.prompts.loader import assemble_system_prompt
from app.repositories.tenant_repo import TenantRepository

_log = logging.getLogger(__name__)

MAX_AGENT_ITERATIONS = 5
MAX_AGENT_TOKENS_PER_TURN = 4000
AGENT_CAP_HIT_MESSAGE = (
    "I'm not able to help with that right now — I've escalated this so a "
    "human can follow up."
)

ToolName = Literal["rag_search", "capture_lead", "escalate"]
ALLOWED_TOOLS: set[ToolName] = {"rag_search", "capture_lead", "escalate"}

_PROMPT_PATH = Path(__file__).resolve().parent.parent / "prompts" / "system_prompt.md"


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
    """Lightweight deterministic plan used when no LLM client is available."""

    tools: list[ToolName]
    reason: str


_TOOL_SCHEMAS: list[dict[str, Any]] = [
    {
        "type": "function",
        "function": {
            "name": "rag_search",
            "description": (
                "Search the current tenant's published CMS content. Use when "
                "the visitor asks a factual question about the tenant."
            ),
            "parameters": RagSearchArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "capture_lead",
            "description": (
                "Record a lead for the current tenant. Use only when the "
                "visitor showed contact / sales / demo / pricing intent."
            ),
            "parameters": CaptureLeadArgs.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "escalate",
            "description": (
                "Hand off to a human teammate. Use when the visitor asks for "
                "a human, when the request is out of scope, or when tenant "
                "content is insufficient."
            ),
            "parameters": EscalateArgs.model_json_schema(),
        },
    },
]


async def _build_system_prompt(tenant_id: Any, session: AsyncSession | None) -> str:
    """Per-request system prompt = PLATFORM_SYSTEM + tenant persona + TOOL_SCHEMAS.

    Per US4 / T090, the prompt loader injects the live tenant persona on
    every turn. Failure to read the persona must not crash the turn — fall
    back to PLATFORM_SYSTEM + default persona block.
    """
    try:
        return await assemble_system_prompt(tenant_id, session)
    except Exception:  # pragma: no cover - defensive
        _log.warning("agent: assemble_system_prompt failed, using fallback", exc_info=True)
        try:
            return _PROMPT_PATH.read_text(encoding="utf-8")
        except OSError:
            return (
                "You are Concierge, a tenant-scoped assistant. Follow the "
                "platform refusal rules and only use the provided tools."
            )


async def run_agent(
    tenant_id: Any,
    message: str,
    session_id: str,
    memory: list[MemoryMessage] | None = None,
    session: AsyncSession | None = None,
    llm_client: GroqAgentClient | None = None,
    route_reason: str = "",
) -> AgentResult:
    """Run the bounded agent path.

    tenant_id must come from the verified widget/backend context. The model,
    visitor, or message text never decides the tenant.
    """
    cleaned_message = message.strip()
    safe_route_reason = redact_text(route_reason) if route_reason else ""

    await _emit_audit_safe(
        session,
        tenant_id=tenant_id,
        action="agent.turn_started",
        metadata={"session_id": session_id, "route_reason": safe_route_reason},
    )

    if not cleaned_message:
        return await _cap_hit_path(
            tenant_id=tenant_id,
            session_id=session_id,
            session=session,
            cap_kind="empty_message",
            iteration_count=0,
            token_total=0,
            used_tools=[],
            citations=[],
        )

    client = llm_client if llm_client is not None else _try_get_default_client()

    if client is None:
        return await _run_deterministic(
            tenant_id=tenant_id,
            session_id=session_id,
            message=cleaned_message,
            memory=memory,
            session=session,
        )

    return await _run_llm_loop(
        tenant_id=tenant_id,
        session_id=session_id,
        message=cleaned_message,
        memory=memory,
        session=session,
        client=client,
    )


# ---------------------------------------------------------------------------
# Real LLM loop (Groq).
# ---------------------------------------------------------------------------


async def _run_llm_loop(
    *,
    tenant_id: Any,
    session_id: str,
    message: str,
    memory: list[MemoryMessage] | None,
    session: AsyncSession | None,
    client: GroqAgentClient,
) -> AgentResult:
    system_prompt = await _build_system_prompt(tenant_id, session)
    messages: list[dict[str, Any]] = [
        {"role": "system", "content": system_prompt},
    ]
    for entry in (memory or [])[-6:]:
        if entry.role in ("user", "assistant"):
            messages.append({"role": entry.role, "content": entry.content})
    messages.append({"role": "user", "content": message})

    used_tools: list[str] = []
    citations: list[dict[str, object]] = []
    cumulative_tokens = 0
    iterations = 0
    captured_lead_results: list[dict[str, Any]] = []

    while iterations < MAX_AGENT_ITERATIONS:
        iterations += 1
        try:
            completion = await client.complete(messages=messages, tools=_TOOL_SCHEMAS)
        except Exception:
            _log.warning("agent loop: groq call failed; falling back to deterministic plan", exc_info=True)
            return await _run_deterministic(
                tenant_id=tenant_id,
                session_id=session_id,
                message=message,
                memory=memory,
                session=session,
            )
        cumulative_tokens += completion.total_tokens

        assistant_msg = completion.message
        tool_calls = getattr(assistant_msg, "tool_calls", None) or []
        text_content = getattr(assistant_msg, "content", None) or ""

        if not tool_calls:
            await _emit_audit_safe(
                session,
                tenant_id=tenant_id,
                action="agent.turn_completed",
                metadata={
                    "session_id": session_id,
                    "iterations": iterations,
                    "token_total": cumulative_tokens,
                    "used_tools": used_tools,
                },
            )
            answer = text_content.strip() or _fallback_text_answer(captured_lead_results)
            return AgentResult(
                answer=answer,
                used_tools=used_tools,
                citations=citations,
                escalated="escalate" in used_tools,
            )

        # Echo the assistant's tool_call request back into history so the
        # tool result messages can attach by tool_call_id.
        messages.append(
            {
                "role": "assistant",
                "content": text_content,
                "tool_calls": [_serialize_tool_call(tc) for tc in tool_calls],
            }
        )

        for tc in tool_calls:
            tool_name = tc.function.name
            raw_args = tc.function.arguments or "{}"
            try:
                parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else dict(raw_args)
            except (TypeError, ValueError):
                parsed_args = {}

            result = await _execute_tool(
                tool_name=tool_name,
                raw_args=parsed_args,
                tenant_id=tenant_id,
                session_id=session_id,
                session=session,
            )

            used_tools.append(tool_name)
            await _emit_audit_safe(
                session,
                tenant_id=tenant_id,
                action="agent.tool_called",
                metadata={
                    "session_id": session_id,
                    "tool_name": tool_name,
                    "iteration": iterations,
                },
            )

            if tool_name == "rag_search":
                raw_chunks = result.get("chunks", [])
                if isinstance(raw_chunks, list):
                    citations.extend(c for c in raw_chunks if isinstance(c, dict))
            elif tool_name == "capture_lead":
                captured_lead_results.append(result)

            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": tc.id,
                    "name": tool_name,
                    "content": json.dumps(_to_jsonable(result)),
                }
            )

            if tool_name == "escalate" and result.get("status") == "escalated":
                await _emit_audit_safe(
                    session,
                    tenant_id=tenant_id,
                    action="agent.turn_completed",
                    metadata={
                        "session_id": session_id,
                        "iterations": iterations,
                        "token_total": cumulative_tokens,
                        "used_tools": used_tools,
                        "exit": "escalated_by_model",
                    },
                )
                return AgentResult(
                    answer="I escalated this conversation to a human so the team can follow up.",
                    used_tools=used_tools,
                    citations=citations,
                    escalated=True,
                )

        if cumulative_tokens >= MAX_AGENT_TOKENS_PER_TURN:
            return await _cap_hit_path(
                tenant_id=tenant_id,
                session_id=session_id,
                session=session,
                cap_kind="token",
                iteration_count=iterations,
                token_total=cumulative_tokens,
                used_tools=used_tools,
                citations=citations,
            )

    # Iteration cap reached without a text return.
    return await _cap_hit_path(
        tenant_id=tenant_id,
        session_id=session_id,
        session=session,
        cap_kind="iteration",
        iteration_count=iterations,
        token_total=cumulative_tokens,
        used_tools=used_tools,
        citations=citations,
    )


async def _execute_tool(
    *,
    tool_name: str,
    raw_args: dict[str, Any],
    tenant_id: Any,
    session_id: str,
    session: AsyncSession | None,
) -> dict[str, Any]:
    """Validate LLM-supplied args via the Pydantic boundary, then execute.

    Any tool the LLM names outside the allowlist returns a structured error
    payload — the loop appends it to history and lets the model recover.
    """
    if tool_name == "rag_search":
        try:
            args = RagSearchArgs(**raw_args)
        except ValidationError as exc:
            return {"status": "invalid_args", "errors": exc.errors()}
        return await rag_search(
            tenant_id=tenant_id,
            query=args.query,
            top_k=args.top_k,
            session=session,
        )

    if tool_name == "capture_lead":
        try:
            args = CaptureLeadArgs(**raw_args)
        except ValidationError as exc:
            return {"status": "invalid_args", "errors": exc.errors()}
        return await capture_lead(
            tenant_id=tenant_id,
            session_id=session_id,
            name=args.name,
            contact=args.contact,
            intent=args.intent,
            session=session,
        )

    if tool_name == "escalate":
        try:
            args = EscalateArgs(**raw_args)
        except ValidationError as exc:
            return {"status": "invalid_args", "errors": exc.errors()}
        return await escalate(
            tenant_id=tenant_id,
            conversation_id=session_id,
            reason=args.reason,
            session=session,
        )

    return {"status": "tool_not_allowed", "tool_name": tool_name}


async def _cap_hit_path(
    *,
    tenant_id: Any,
    session_id: str,
    session: AsyncSession | None,
    cap_kind: str,
    iteration_count: int,
    token_total: int,
    used_tools: list[str],
    citations: list[dict[str, object]],
) -> AgentResult:
    """Force one escalate call (NEVER capture_lead) and return the safe message."""
    escalate_reason = "agent_cap_hit"
    escalate_result = await escalate(
        tenant_id=tenant_id,
        conversation_id=session_id,
        reason=escalate_reason,
        session=session,
    )
    used_tools.append("escalate")

    if cap_kind == "iteration":
        action = "agent.iteration_cap_hit"
    elif cap_kind == "token":
        action = "agent.token_cap_hit"
    else:
        action = "agent.iteration_cap_hit"

    await _emit_audit_safe(
        session,
        tenant_id=tenant_id,
        action=action,
        metadata={
            "session_id": session_id,
            "iteration_count": iteration_count,
            "token_total": token_total,
            "exit": cap_kind,
        },
    )

    return AgentResult(
        answer=AGENT_CAP_HIT_MESSAGE,
        used_tools=used_tools,
        citations=citations,
        escalated=escalate_result.get("status") == "escalated",
    )


def _serialize_tool_call(tc: Any) -> dict[str, Any]:
    return {
        "id": tc.id,
        "type": "function",
        "function": {
            "name": tc.function.name,
            "arguments": tc.function.arguments or "{}",
        },
    }


def _to_jsonable(payload: dict[str, Any]) -> dict[str, Any]:
    """Best-effort coercion of UUIDs and other non-JSON types to strings."""
    safe: dict[str, Any] = {}
    for key, value in payload.items():
        if isinstance(value, UUID):
            safe[key] = str(value)
        elif isinstance(value, (str, int, float, bool)) or value is None:
            safe[key] = value
        elif isinstance(value, (list, tuple)):
            safe[key] = [str(v) if isinstance(v, UUID) else v for v in value]
        else:
            safe[key] = str(value)
    return safe


def _fallback_text_answer(captured_lead_results: list[dict[str, Any]]) -> str:
    if captured_lead_results and captured_lead_results[-1].get("status") == "captured":
        return "I captured your details — the team will reach out shortly."
    return "I've recorded this conversation. The team will follow up if needed."


# ---------------------------------------------------------------------------
# Deterministic fallback (used when no LLM client is available).
# ---------------------------------------------------------------------------


async def _run_deterministic(
    *,
    tenant_id: Any,
    session_id: str,
    message: str,
    memory: list[MemoryMessage] | None,
    session: AsyncSession | None,
) -> AgentResult:
    """The pre-LLM deterministic planner — kept for dev / tests / cold-start."""
    budget_used = _rough_token_count(message) + _memory_token_count(memory)
    if MAX_AGENT_TOKENS_PER_TURN - budget_used <= 0:
        return await _cap_hit_path(
            tenant_id=tenant_id,
            session_id=session_id,
            session=session,
            cap_kind="token",
            iteration_count=0,
            token_total=budget_used,
            used_tools=[],
            citations=[],
        )

    plan = _plan_tools(message)
    used_tools: list[str] = []
    citations: list[dict[str, object]] = []
    answer_parts: list[str] = []
    escalated = False

    for iteration, tool_name in enumerate(plan.tools, start=1):
        if iteration > MAX_AGENT_ITERATIONS:
            break

        if tool_name not in ALLOWED_TOOLS:
            return await _cap_hit_path(
                tenant_id=tenant_id,
                session_id=session_id,
                session=session,
                cap_kind="iteration",
                iteration_count=iteration,
                token_total=budget_used,
                used_tools=used_tools,
                citations=citations,
            )

        result = await _call_tool(
            tool_name=tool_name,
            tenant_id=tenant_id,
            session_id=session_id,
            message=message,
            session=session,
            reason=plan.reason,
        )
        used_tools.append(tool_name)
        await _emit_audit_safe(
            session,
            tenant_id=tenant_id,
            action="agent.tool_called",
            metadata={
                "session_id": session_id,
                "tool_name": tool_name,
                "iteration": iteration,
            },
        )

        if tool_name == "rag_search":
            answer_parts.append(str(result.get("answer", "")))
            raw_chunks = result.get("chunks", [])
            if isinstance(raw_chunks, list):
                citations.extend(c for c in raw_chunks if isinstance(c, dict))
        elif tool_name == "capture_lead":
            if result.get("status") == "rate_limited":
                answer_parts.append(
                    "I've already captured your details — the team will reach out shortly."
                )
            elif result.get("has_contact") is False:
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

    await _emit_audit_safe(
        session,
        tenant_id=tenant_id,
        action="agent.turn_completed",
        metadata={
            "session_id": session_id,
            "iterations": min(len(used_tools), MAX_AGENT_ITERATIONS),
            "token_total": budget_used,
            "used_tools": used_tools,
            "exit": "deterministic_fallback",
        },
    )

    if not answer_parts:
        return await _cap_hit_path(
            tenant_id=tenant_id,
            session_id=session_id,
            session=session,
            cap_kind="iteration",
            iteration_count=len(used_tools),
            token_total=budget_used,
            used_tools=used_tools,
            citations=citations,
        )

    return AgentResult(
        answer="\n\n".join(part for part in answer_parts if part.strip()),
        used_tools=used_tools,
        citations=citations,
        escalated=escalated,
    )


def _plan_tools(message: str) -> _AgentPlan:
    """Deterministic stand-in tool plan."""
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
    tenant_id: Any,
    session_id: str,
    message: str,
    session: AsyncSession | None,
    reason: str,
) -> dict[str, Any]:
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
            session_id=session_id,
            name=name,
            contact=contact,
            intent=message,
            session=session,
        )
    return await escalate(
        tenant_id=tenant_id,
        conversation_id=session_id,
        reason=reason,
        session=session,
    )


def _needs_human(lowered_message: str) -> bool:
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
    question_terms = ("what", "how", "when", "where", "why", "which", "do you", "can you", "?")
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
    return max(1, len(text.split()))


def _memory_token_count(memory: list[MemoryMessage] | None) -> int:
    if not memory:
        return 0
    return sum(_rough_token_count(item.content) for item in memory[-6:])


# ---------------------------------------------------------------------------
# Audit emission and lazy client construction.
# ---------------------------------------------------------------------------


_DEFAULT_CLIENT: GroqAgentClient | None = None
_DEFAULT_CLIENT_RESOLVED: bool = False


def _try_get_default_client() -> GroqAgentClient | None:
    global _DEFAULT_CLIENT, _DEFAULT_CLIENT_RESOLVED
    if not _DEFAULT_CLIENT_RESOLVED:
        _DEFAULT_CLIENT = try_build_default_groq_client()
        _DEFAULT_CLIENT_RESOLVED = True
    return _DEFAULT_CLIENT


def reset_default_client_for_tests() -> None:
    """Reset the cached default client (tests only)."""
    global _DEFAULT_CLIENT, _DEFAULT_CLIENT_RESOLVED
    _DEFAULT_CLIENT = None
    _DEFAULT_CLIENT_RESOLVED = False


def _coerce_uuid(value: Any) -> UUID:
    if isinstance(value, UUID):
        return value
    return UUID(str(value))


async def _emit_audit_safe(
    session: AsyncSession | None,
    *,
    tenant_id: Any,
    action: str,
    metadata: dict[str, Any],
    actor_role: str = "agent",
) -> None:
    """Emit an audit entry; swallow errors so a failed audit never breaks the loop."""
    if session is None:
        return
    try:
        repo = TenantRepository(session)
        await repo.add_audit_log(
            tenant_id=_coerce_uuid(tenant_id),
            actor_id=None,
            actor_role=actor_role,
            action=action,
            metadata=metadata,
        )
    except Exception:  # pragma: no cover - defensive
        _log.warning("agent audit emission failed: action=%s", action, exc_info=True)
