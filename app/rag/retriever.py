# Owner: Nasser
"""Tenant-filtered RAG retrieval.

Every retrieval query must filter by tenant_id. Until pgvector is wired by the
team, this retriever uses tenant-scoped CMS rows and lexical scoring so the
chat flow is real and testable without cross-tenant leakage.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CmsPage


@dataclass(frozen=True)
class RagChunk:
    """Retrieved tenant-scoped CMS chunk."""

    chunk_id: str
    tenant_id: int
    page_id: int
    text: str
    score: float
    source_title: str


def chunk_text(text: str, chunk_size: int = 700, overlap: int = 120) -> list[str]:
    """Split CMS text into fixed-size overlapping chunks."""

    cleaned = " ".join(text.split())
    if not cleaned:
        return []

    chunks: list[str] = []
    start = 0
    while start < len(cleaned):
        end = start + chunk_size
        chunks.append(cleaned[start:end])
        if end >= len(cleaned):
            break
        start = max(0, end - overlap)

    return chunks


async def retrieve_chunks(
    tenant_id: int,
    query: str,
    top_k: int = 5,
    session: AsyncSession | None = None,
) -> list[dict[str, object]]:
    """Retrieve tenant-scoped chunks.

    The SQL query is explicitly scoped by CmsPage.tenant_id. When pgvector is
    added, keep this tenant predicate in the vector query as well.
    """

    if session is None:
        return []

    result = await session.execute(
        select(CmsPage).where(CmsPage.tenant_id == tenant_id)
    )
    pages = list(result.scalars().all())

    query_terms = _tokenize(query)
    candidates: list[RagChunk] = []

    for page in pages:
        for index, chunk in enumerate(chunk_text(page.body)):
            score = _score_chunk(query_terms, chunk)
            if score <= 0 and query_terms:
                continue
            candidates.append(
                RagChunk(
                    chunk_id=f"cms-{page.id}-{index}",
                    tenant_id=tenant_id,
                    page_id=page.id,
                    text=chunk,
                    score=score,
                    source_title=page.title,
                )
            )

    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)[:top_k]
    return [chunk.__dict__ for chunk in ranked]


def _tokenize(text: str) -> set[str]:
    """Tokenize a query/chunk for lightweight lexical matching."""

    return {token for token in re.findall(r"[a-zA-Z0-9]+", text.lower()) if len(token) > 2}


def _score_chunk(query_terms: set[str], chunk: str) -> float:
    """Return a simple overlap score for local development retrieval."""

    if not query_terms:
        return 0.0

    chunk_terms = _tokenize(chunk)
    if not chunk_terms:
        return 0.0

    overlap = query_terms.intersection(chunk_terms)
    return round(len(overlap) / len(query_terms), 4)
