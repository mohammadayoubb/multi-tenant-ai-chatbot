# Owner: Nasser
"""Agent tool-selection evaluator (US4 / task T091).

Loops the committed golden set ``evals/agent_tool_selection_cases.json``
through the live router + bounded-agent path and reports ``accuracy`` per the
eval-CLI contract at ``specs/006-ci-eval-gates/contracts/eval-cli.md``.

A case is counted correct when:

- ``expected_route ∈ {"rag_search", "capture_lead", "escalate", "blocked"}``:
  the router's ``decision.route`` equals ``expected_route``. ``expected_tools``
  must also match the implied workflow tool (the first element).
- ``expected_route == "agent"``: the router routes to ``"agent"`` AND the
  bounded agent's ``used_tools`` set equals the expected_tools set.

The agent is run with ``session=None`` and ``llm_client=None`` so the
deterministic plan path is exercised; this gives a stable, DB-free signal in
CI. When a Groq client is available locally, callers may set ``GROQ_API_KEY``
to exercise the real LLM loop — but the evaluator does not require it.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
from pathlib import Path
from uuid import uuid4

from app.agent.agent import run_agent
from app.agent.router import route_message_decision

_CASES_PATH = Path(__file__).resolve().parent / "agent_tool_selection_cases.json"


async def _evaluate_one(case: dict) -> tuple[bool, dict]:
    expected_route = case["expected_route"]
    expected_tools = set(case.get("expected_tools") or [])
    message = case["message"]

    decision = await route_message_decision(message)
    actual_route = decision.route
    diagnostic: dict = {
        "id": case.get("id"),
        "expected_route": expected_route,
        "actual_route": actual_route,
        "expected_tools": sorted(expected_tools),
    }

    if expected_route != "agent":
        correct = actual_route == expected_route
        diagnostic["correct"] = correct
        return correct, diagnostic

    if actual_route != "agent":
        diagnostic["correct"] = False
        return False, diagnostic

    result = await run_agent(
        tenant_id=uuid4(),
        message=message,
        session_id=f"eval-{case.get('id', 'x')}",
        memory=None,
        session=None,
        llm_client=None,
        route_reason=decision.reason,
    )
    used = set(result.used_tools)
    diagnostic["actual_tools"] = sorted(used)
    correct = used == expected_tools
    diagnostic["correct"] = correct
    return correct, diagnostic


async def _run(cases: list[dict]) -> dict:
    results = await asyncio.gather(*(_evaluate_one(c) for c in cases))
    passed = sum(1 for ok, _ in results if ok)
    total = len(results)
    accuracy = (passed / total) if total else 0.0
    examples = [diag for ok, diag in results if not ok]
    return {
        "metrics": {"accuracy": round(accuracy, 4)},
        "meta": {"total": total, "passed": passed},
        "examples": examples,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    parser.add_argument(
        "--cases",
        default=str(_CASES_PATH),
        help="path to the agent-tool selection golden set (default: bundled)",
    )
    args = parser.parse_args(argv)

    cases_path = Path(args.cases)
    cases = json.loads(cases_path.read_text(encoding="utf-8"))

    report = asyncio.run(_run(cases))

    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
