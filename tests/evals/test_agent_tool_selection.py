# Owner: Nasser
"""Golden-set eval for Section B agent/tool routing.

This test checks that common visitor messages choose the correct workflow path
or bounded-agent tool plan.

It intentionally uses local fallback routing instead of the live modelserver so
the eval is deterministic in CI.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.agent.agent import _plan_tools
from app.agent.router import route_message_decision

CASES_PATH = Path("evals/agent_tool_selection_cases.json")


def _load_cases() -> list[dict[str, Any]]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


@pytest.mark.asyncio
@pytest.mark.parametrize("case", _load_cases(), ids=lambda case: case["id"])
async def test_agent_tool_selection_golden_set(case: dict[str, Any]) -> None:
    """Router and agent planner should match the committed golden set."""

    decision = await route_message_decision(
        case["message"],
        modelserver_client=None,
    )

    assert decision.route == case["expected_route"], case["reason"]

    expected_tools = case["expected_tools"]

    if decision.route == "agent":
        plan = _plan_tools(case["message"])
        assert plan.tools == expected_tools, case["reason"]
    elif decision.route == "rag_search":
        assert expected_tools == ["rag_search"], case["reason"]
    elif decision.route == "capture_lead":
        assert expected_tools == ["capture_lead"], case["reason"]
    elif decision.route == "escalate":
        assert expected_tools == ["escalate"], case["reason"]
    elif decision.route == "blocked":
        assert expected_tools == [], case["reason"]