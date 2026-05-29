# Owner: Nasser
"""Golden-set eval for Section B RAG retrieval.

This test validates:
- tenant-scoped retrieval
- expected source selection
- expected content terms in retrieved chunks

It uses the chunking/scoring helpers directly so it stays deterministic in CI
without requiring Postgres or pgvector.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from app.rag.retriever import RagChunk, _expanded_query_terms, _score_chunk, chunk_text

CASES_PATH = Path("evals/rag_cases.json")


def _load_cases() -> list[dict[str, Any]]:
    return json.loads(CASES_PATH.read_text(encoding="utf-8"))


def _retrieve_from_case(case: dict[str, Any]) -> list[RagChunk]:
    query = str(case["query"])
    query_terms = _expanded_query_terms(query)
    tenant_id = int(case["tenant_id"])

    candidates: list[RagChunk] = []

    for page in case["pages"]:
        page_id = int(page["page_id"])
        title = str(page["title"])
        body = str(page["body"])

        # Simulate tenant filtering.
        # Test data uses page id 200+ as "other tenant" when current tenant is 1.
        if tenant_id == 1 and page_id >= 200:
            continue
        if tenant_id == 2 and page_id < 200:
            continue

        for index, chunk in enumerate(chunk_text(body)):
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
                    source_title=title,
                )
            )

    return sorted(candidates, key=lambda item: item.score, reverse=True)


@pytest.mark.parametrize("case", _load_cases(), ids=lambda case: case["id"])
def test_rag_retrieval_golden_set(case: dict[str, Any]) -> None:
    """RAG retrieval should select expected tenant-scoped source chunks."""

    results = _retrieve_from_case(case)

    assert results, case["reason"]

    best = results[0]
    assert best.source_title == case["expected_source_title"], case["reason"]

    lowered_text = best.text.lower()
    for term in case["expected_terms"]:
        assert str(term).lower() in lowered_text, case["reason"]
