# Owner: Nasser
"""Tenant-filtered RAG retrieval.

Every retrieval query must filter by tenant_id. Until pgvector is wired by the
team, this retriever uses tenant-scoped CMS rows and lexical scoring so the
chat flow is real and testable without cross-tenant leakage.

When pgvector is added, keep the same rule:
WHERE tenant_id = :tenant_id
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CmsPage

_DEFAULT_CHUNK_SIZE = 700
_DEFAULT_CHUNK_OVERLAP = 120
_MAX_TOP_K = 8


@dataclass(frozen=True)
class RagChunk:
    """Retrieved tenant-scoped CMS chunk."""

    chunk_id: str
    tenant_id: UUID
    page_id: UUID
    text: str
    score: float
    source_title: str
    source_type: str = "cms_page"


def chunk_text(
    text: str,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    overlap: int = _DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split CMS text into fixed-size overlapping chunks.

    This is the current non-naive chunking choice: overlapping chunks preserve
    context across chunk boundaries while staying simple and explainable.
    """

    safe_chunk_size = max(100, chunk_size)
    safe_overlap = max(0, min(overlap, safe_chunk_size - 1))

    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0

    while start < len(cleaned):
        end = start + safe_chunk_size
        chunks.append(cleaned[start:end])

        if end >= len(cleaned):
            break

        start = end - safe_overlap

    return chunks


async def retrieve_chunks(
    tenant_id: UUID,
    query: str,
    top_k: int = 5,
    session: AsyncSession | None = None,
) -> list[dict[str, object]]:
    """Retrieve tenant-scoped chunks from CMS content.

    The SQL query is explicitly scoped by CmsPage.tenant_id. This is part of
    the isolation boundary, not an optional filter.
    """

    cleaned_query = query.strip()
    if session is None or not cleaned_query:
        return []

    safe_top_k = max(1, min(top_k, _MAX_TOP_K))

    result = await session.execute(
        select(CmsPage)
        .where(CmsPage.tenant_id == tenant_id)
        .order_by(CmsPage.id.asc())
    )
    pages = list(result.scalars().all())

    query_terms = _tokenize(cleaned_query)
    if not query_terms:
        return []

    candidates: list[RagChunk] = []

    for page in pages:
        title = str(getattr(page, "title", "CMS content") or "CMS content")
        body = str(getattr(page, "body", "") or "")

        for index, chunk in enumerate(chunk_text(body)):
            score = _score_chunk(query_terms, cleaned_query, chunk)
            if score <= 0:
                continue

            candidates.append(
                RagChunk(
                    chunk_id=f"cms-{page.id}-{index}",
                    tenant_id=tenant_id,
                    page_id=page.id,
                    text=chunk,
                    score=score,
                    source_title=title,
                )
            )

    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)[:safe_top_k]
    return [asdict(chunk) for chunk in ranked]


def _tokenize(text: str) -> set[str]:
    """Tokenize a query/chunk for lightweight lexical matching."""

    return {
        token
        for token in re.findall(r"[a-zA-Z0-9]+", text.lower())
        if len(token) > 2
    }


def _score_chunk(query_terms: set[str], raw_query: str, chunk: str) -> float:
    """Return a simple lexical score for local development retrieval."""

    chunk_terms = _tokenize(chunk)
    if not query_terms or not chunk_terms:
        return 0.0

    overlap = query_terms.intersection(chunk_terms)
    overlap_score = len(overlap) / len(query_terms)

    phrase_boost = 0.0
    lowered_chunk = chunk.lower()
    lowered_query = raw_query.lower()

    if lowered_query and lowered_query in lowered_chunk:
        phrase_boost = 0.25

    return round(overlap_score + phrase_boost, 4)
