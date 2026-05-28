# Owner: Nasser

"""Section B eval summary report.

This script prints simple Owner B metrics for demo/readme use:

- agent/tool routing golden-set count
- RAG retrieval golden-set count

Run from repo root:

    python evals/section_b_report.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


# ruff: noqa: E402
from app.agent.agent import _plan_tools
from app.agent.router import _fallback_rule_decision
from app.rag.retriever import RagChunk, _score_chunk, _tokenize, chunk_text


AGENT_CASES_PATH = ROOT / "evals" / "agent_tool_selection_cases.json"
RAG_CASES_PATH = ROOT / "evals" / "rag_cases.json"


def main() -> None:
    """Print Section B eval report."""

    agent_passed, agent_total = evaluate_agent_tool_selection()
    rag_passed, rag_total = evaluate_rag_retrieval()

    print("Section B Eval Report")
    print("=====================")
    print(f"Agent/tool selection: {agent_passed}/{agent_total} passed")
    print(f"RAG retrieval:        {rag_passed}/{rag_total} passed")

    if agent_passed == agent_total and rag_passed == rag_total:
        print("\nStatus: PASS")
        return

    print("\nStatus: FAIL")
    raise SystemExit(1)


def evaluate_agent_tool_selection() -> tuple[int, int]:
    """Evaluate router route and agent tool plan against golden cases."""

    cases = _load_json(AGENT_CASES_PATH)
    passed = 0

    for case in cases:
        decision = _fallback_rule_decision(str(case["message"]))
        expected_route = str(case["expected_route"])
        expected_tools = list(case["expected_tools"])

        route_ok = decision.route == expected_route
        tools_ok = True

        if decision.route == "agent":
            tools_ok = list(_plan_tools(str(case["message"])).tools) == expected_tools
        elif decision.route == "rag_search":
            tools_ok = expected_tools == ["rag_search"]
        elif decision.route == "capture_lead":
            tools_ok = expected_tools == ["capture_lead"]
        elif decision.route == "escalate":
            tools_ok = expected_tools == ["escalate"]
        elif decision.route == "blocked":
            tools_ok = expected_tools == []

        if route_ok and tools_ok:
            passed += 1

    return passed, len(cases)


def evaluate_rag_retrieval() -> tuple[int, int]:
    """Evaluate deterministic RAG retrieval cases."""

    cases = _load_json(RAG_CASES_PATH)
    passed = 0

    for case in cases:
        results = _retrieve_from_case(case)

        if not results:
            continue

        best = results[0]
        expected_source = str(case["expected_source_title"])
        expected_terms = [str(term).lower() for term in case["expected_terms"]]

        source_ok = best.source_title == expected_source
        text = best.text.lower()
        terms_ok = all(term in text for term in expected_terms)

        if source_ok and terms_ok:
            passed += 1

    return passed, len(cases)


def _retrieve_from_case(case: dict[str, Any]) -> list[RagChunk]:
    """Run deterministic retrieval over inline case pages."""

    query = str(case["query"])
    query_terms = _tokenize(query)
    query_terms.update(_semantic_query_expansions(query))
    tenant_id = int(case["tenant_id"])

    candidates: list[RagChunk] = []

    for page in case["pages"]:
        page_id = int(page["page_id"])

        # Simulate tenant filtering for this small offline golden set.
        if tenant_id == 1 and page_id >= 200:
            continue
        if tenant_id == 2 and page_id < 200:
            continue

        for index, chunk in enumerate(chunk_text(str(page["body"]))):
            score = _score_chunk(query_terms, query, chunk)
            if score <= 0:
                continue

            candidates.append(
                RagChunk(
                    chunk_id=f"cms-{page_id}-{index}",
                    tenant_id=tenant_id,
                    page_id=page_id,
                    text=chunk,
                    score=score,
                    source_title=str(page["title"]),
                )
            )

    return sorted(candidates, key=lambda item: item.score, reverse=True)


def _semantic_query_expansions(query: str) -> set[str]:
    """Small deterministic synonyms for the current lexical RAG fallback."""

    lowered = query.lower()
    expansions: set[str] = set()

    if "membership" in lowered or "cost" in lowered or "price" in lowered:
        expansions.update({"membership", "memberships", "month", "dollars", "pricing"})

    if "open" in lowered or "saturday" in lowered or "hours" in lowered:
        expansions.update({"open", "saturday", "hours"})

    if "located" in lowered or "where" in lowered or "location" in lowered:
        expansions.update({"located", "location", "station", "library"})

    if "cancellation" in lowered or "cancel" in lowered:
        expansions.update({"cancellation", "policy", "hours"})

    return expansions


def _load_json(path: Path) -> list[dict[str, Any]]:
    """Load a JSON list from disk."""

    return json.loads(path.read_text(encoding="utf-8"))


if __name__ == "__main__":
    main()