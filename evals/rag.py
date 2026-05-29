# Owner: Nasser
"""Deterministic RAG evaluator.

Contract: specs/006-ci-eval-gates/contracts/eval-cli.md
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

# ruff: noqa: E402
from app.rag.retriever import RagChunk, _expanded_query_terms, _score_chunk, chunk_text

CASES_PATH = ROOT / "evals" / "rag_cases.json"


def evaluate(cases: list[dict[str, Any]]) -> dict[str, Any]:
    results = [_evaluate_case(case) for case in cases]
    total = len(results) or 1

    return {
        "metrics": {
            "hit_at_5": round(
                sum(1 for result in results if result["hit_at_5"]) / total,
                4,
            ),
            "mrr": round(
                sum(float(result["reciprocal_rank"]) for result in results) / total,
                4,
            ),
            "faithfulness": round(
                sum(1 for result in results if result["faithful"]) / total,
                4,
            ),
        },
        "cases": results,
    }


def _evaluate_case(case: dict[str, Any]) -> dict[str, Any]:
    ranked = _retrieve_from_case(case)
    expected_source = str(case["expected_source_title"])
    expected_terms = [str(term).lower() for term in case["expected_terms"]]

    matching_rank = next(
        (
            index + 1
            for index, result in enumerate(ranked)
            if result.source_title == expected_source
        ),
        None,
    )
    best = ranked[0] if ranked else None
    best_text = best.text.lower() if best else ""

    return {
        "id": str(case["id"]),
        "expected_source_title": expected_source,
        "top_source_title": best.source_title if best else None,
        "rank": matching_rank,
        "hit_at_5": matching_rank is not None and matching_rank <= 5,
        "reciprocal_rank": 0.0 if matching_rank is None else 1.0 / matching_rank,
        "faithful": all(term in best_text for term in expected_terms),
    }


def _retrieve_from_case(case: dict[str, Any]) -> list[RagChunk]:
    query = str(case["query"])
    query_terms = _expanded_query_terms(query)
    tenant_id = int(case["tenant_id"])

    candidates: list[RagChunk] = []
    for page in case["pages"]:
        page_id = int(page["page_id"])
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True)
    args = parser.parse_args(argv)

    payload = evaluate(json.loads(CASES_PATH.read_text(encoding="utf-8")))
    out_path = Path(args.output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main())
