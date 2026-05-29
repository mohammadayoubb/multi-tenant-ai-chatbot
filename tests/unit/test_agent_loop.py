# Owner: Nasser
"""Unit tests for the bounded agent loop (task T061, contract C-T2-3).

Covers the cap-hit invariants that protect the platform from runaway cost
and runaway tool execution:

- The loop halts at ``MAX_AGENT_ITERATIONS`` even if the LLM keeps emitting
  tool_use blocks.
- On the cap-hit path the loop fires ``escalate`` exactly once with
  ``reason="agent_cap_hit"`` — and it MUST NOT call ``capture_lead`` (per
  C-T2-3's "escalate is the only safe default under uncertainty" clause).
- The cap-hit path returns the safe-default visitor message.
- An analogous test verifies the token-cap branch (``MAX_AGENT_TOKENS_PER_TURN``).
- Standard exit (LLM returns text) returns the assistant's text answer.

These tests use a synthetic Groq client stub — they never hit the network
and don't require GROQ_API_KEY.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any
from uuid import uuid4

import pytest

import app.agent.agent as agent_module
from app.agent.agent import (
    AGENT_CAP_HIT_MESSAGE,
    MAX_AGENT_ITERATIONS,
    MAX_AGENT_TOKENS_PER_TURN,
    run_agent,
)


# ---------------------------------------------------------------------------
# Synthetic Groq client (mimics the GroqAgentClient.complete() interface).
# ---------------------------------------------------------------------------


@dataclass
class _StubFunction:
    name: str
    arguments: str


@dataclass
class _StubToolCall:
    id: str
    function: _StubFunction
    type: str = "function"


@dataclass
class _StubMessage:
    content: str | None = None
    tool_calls: list[_StubToolCall] = field(default_factory=list)


@dataclass
class _StubCompletion:
    message: _StubMessage
    total_tokens: int


class _StubGroqClient:
    """Drives a scripted sequence of completions through the loop."""

    def __init__(self, completions: list[_StubCompletion]) -> None:
        self._completions = list(completions)
        self.calls: list[dict[str, Any]] = []

    @property
    def model(self) -> str:
        return "stub-llama-3.3-70b"

    async def complete(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> _StubCompletion:
        self.calls.append({"messages": list(messages), "tools": tools})
        if not self._completions:
            # Default: text answer "ok" so the loop terminates cleanly.
            return _StubCompletion(message=_StubMessage(content="ok"), total_tokens=10)
        return self._completions.pop(0)


def _tool_call_completion(name: str, arguments_json: str, *, tokens: int = 50) -> _StubCompletion:
    tc = _StubToolCall(
        id=f"call_{name}_{uuid4().hex[:6]}",
        function=_StubFunction(name=name, arguments=arguments_json),
    )
    return _StubCompletion(
        message=_StubMessage(content=None, tool_calls=[tc]),
        total_tokens=tokens,
    )


def _text_completion(content: str, *, tokens: int = 25) -> _StubCompletion:
    return _StubCompletion(
        message=_StubMessage(content=content),
        total_tokens=tokens,
    )


# ---------------------------------------------------------------------------
# Tool spies — capture which tools fired, with what trusted args.
# ---------------------------------------------------------------------------


class _ToolSpy:
    def __init__(self) -> None:
        self.rag_search_calls: list[dict[str, Any]] = []
        self.capture_lead_calls: list[dict[str, Any]] = []
        self.escalate_calls: list[dict[str, Any]] = []


@pytest.fixture
def tool_spy(monkeypatch: pytest.MonkeyPatch) -> _ToolSpy:
    """Patch the three tools imported into agent_module with recording stubs."""
    spy = _ToolSpy()

    async def _fake_rag_search(**kwargs: Any) -> dict[str, Any]:
        spy.rag_search_calls.append(kwargs)
        return {"status": "ok", "answer": "stubbed answer", "chunks": []}

    async def _fake_capture_lead(**kwargs: Any) -> dict[str, Any]:
        spy.capture_lead_calls.append(kwargs)
        return {"status": "captured", "lead_id": "stub", "has_contact": True}

    async def _fake_escalate(**kwargs: Any) -> dict[str, Any]:
        spy.escalate_calls.append(kwargs)
        return {"status": "escalated", "ticket_id": "stub-ticket"}

    monkeypatch.setattr(agent_module, "rag_search", _fake_rag_search)
    monkeypatch.setattr(agent_module, "capture_lead", _fake_capture_lead)
    monkeypatch.setattr(agent_module, "escalate", _fake_escalate)
    return spy


# ---------------------------------------------------------------------------
# Standard exit — LLM returns text on first turn.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_returns_text_answer_on_first_turn(tool_spy: _ToolSpy) -> None:
    client = _StubGroqClient([_text_completion("Here is the answer.")])
    result = await run_agent(
        tenant_id=uuid4(),
        message="anything",
        session_id="text-exit",
        llm_client=client,
    )
    assert result.answer == "Here is the answer."
    assert result.used_tools == []
    assert not tool_spy.escalate_calls
    assert not tool_spy.capture_lead_calls


# ---------------------------------------------------------------------------
# Iteration cap — synthetic LLM returns 6 sequential tool_use blocks.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_halts_at_iteration_cap_and_escalates_once(
    tool_spy: _ToolSpy,
) -> None:
    """LLM returns rag_search forever — loop must clamp to MAX_AGENT_ITERATIONS
    and fire escalate exactly once with reason=agent_cap_hit. capture_lead
    MUST NEVER fire on the cap-hit path."""
    rag_args = '{"query": "anything"}'
    completions = [
        _tool_call_completion("rag_search", rag_args, tokens=100)
        for _ in range(MAX_AGENT_ITERATIONS + 5)
    ]
    client = _StubGroqClient(completions)

    result = await run_agent(
        tenant_id=uuid4(),
        message="multi-step question",
        session_id="iter-cap",
        llm_client=client,
    )

    # The client was driven up to (but not beyond) the iteration cap.
    assert len(client.calls) == MAX_AGENT_ITERATIONS

    # Tool spies: rag_search fired once per iteration, escalate exactly once,
    # capture_lead never.
    assert len(tool_spy.rag_search_calls) == MAX_AGENT_ITERATIONS
    assert len(tool_spy.escalate_calls) == 1
    assert tool_spy.escalate_calls[0]["reason"] == "agent_cap_hit"
    assert tool_spy.capture_lead_calls == []

    # Safe-default visitor message returned.
    assert result.answer == AGENT_CAP_HIT_MESSAGE
    assert "escalate" in result.used_tools


# ---------------------------------------------------------------------------
# Token cap — cumulative tokens cross the budget mid-loop.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_loop_halts_at_token_cap_and_escalates_once(
    tool_spy: _ToolSpy,
) -> None:
    """One iteration whose usage punches over MAX_AGENT_TOKENS_PER_TURN
    must trigger the token-cap branch, fire escalate once, never capture_lead."""
    rag_args = '{"query": "anything"}'
    big_token_burn = MAX_AGENT_TOKENS_PER_TURN + 500
    client = _StubGroqClient(
        [_tool_call_completion("rag_search", rag_args, tokens=big_token_burn)]
    )

    result = await run_agent(
        tenant_id=uuid4(),
        message="huge context",
        session_id="token-cap",
        llm_client=client,
    )

    # Exactly one LLM call before the loop bailed.
    assert len(client.calls) == 1
    assert len(tool_spy.rag_search_calls) == 1
    assert len(tool_spy.escalate_calls) == 1
    assert tool_spy.escalate_calls[0]["reason"] == "agent_cap_hit"
    assert tool_spy.capture_lead_calls == []
    assert result.answer == AGENT_CAP_HIT_MESSAGE


# ---------------------------------------------------------------------------
# Model-driven escalate exits cleanly without cap-hit semantics.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_model_initiated_escalate_exits_with_handoff_message(
    tool_spy: _ToolSpy,
) -> None:
    """When the LLM itself calls escalate, the loop exits via the
    'escalated_by_model' path — NOT the cap-hit path. Reason on the
    escalate call must be the LLM-supplied one, not 'agent_cap_hit'."""
    escalate_args = '{"reason": "Visitor explicitly asked for a human."}'
    client = _StubGroqClient([_tool_call_completion("escalate", escalate_args)])

    result = await run_agent(
        tenant_id=uuid4(),
        message="i want a human",
        session_id="model-escalate",
        llm_client=client,
    )

    assert len(tool_spy.escalate_calls) == 1
    assert tool_spy.escalate_calls[0]["reason"] == "Visitor explicitly asked for a human."
    assert result.escalated is True
    assert "escalated" in result.answer.lower()


# ---------------------------------------------------------------------------
# Empty message short-circuits via cap-hit path.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_empty_message_triggers_safe_escalate(tool_spy: _ToolSpy) -> None:
    client = _StubGroqClient([])  # never invoked
    result = await run_agent(
        tenant_id=uuid4(),
        message="   ",
        session_id="empty",
        llm_client=client,
    )
    assert client.calls == []
    assert len(tool_spy.escalate_calls) == 1
    assert tool_spy.escalate_calls[0]["reason"] == "agent_cap_hit"
    assert result.answer == AGENT_CAP_HIT_MESSAGE


# ---------------------------------------------------------------------------
# Invalid tool args from the LLM are caught at the Pydantic boundary; the
# loop appends a structured error to history and proceeds — the trusted
# tools are NEVER invoked with the malformed payload.
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_invalid_tool_args_do_not_invoke_tool(tool_spy: _ToolSpy) -> None:
    """LLM sends rag_search with empty query (violates min_length=1).
    The Pydantic boundary catches it; tool is NOT invoked; next turn must
    still terminate cleanly."""
    bad_rag = '{"query": ""}'
    client = _StubGroqClient(
        [
            _tool_call_completion("rag_search", bad_rag, tokens=20),
            _text_completion("Recovered with a text answer.", tokens=15),
        ]
    )
    result = await run_agent(
        tenant_id=uuid4(),
        message="anything",
        session_id="bad-args",
        llm_client=client,
    )
    assert tool_spy.rag_search_calls == []  # never reached the real tool
    assert result.answer == "Recovered with a text answer."
