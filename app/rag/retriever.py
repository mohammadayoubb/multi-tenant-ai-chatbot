# Owner: Nasser
"""Tenant-filtered RAG retrieval.

Retrieval prefers indexed ``rag_chunks`` rows and falls back to published CMS
pages only when the index is empty or unavailable. Every database path filters
by the trusted tenant_id.
"""

from __future__ import annotations

import logging
import re
from dataclasses import asdict, dataclass
from typing import Any
from uuid import UUID

from sqlalchemy import select, text as sql_text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import CmsPage

_DEFAULT_CHUNK_SIZE = 700
_DEFAULT_CHUNK_OVERLAP = 120
_MAX_TOP_K = 8

_log = logging.getLogger(__name__)


@dataclass(frozen=True)
class RagChunk:
    """Retrieved tenant-scoped CMS chunk."""

    chunk_id: str
    tenant_id: UUID | int | str
    page_id: UUID | int | str
    text: str
    score: float
    source_title: str
    source_type: str = "cms_page"
    source_url: str | None = None


def chunk_text(
    text: str,
    chunk_size: int = _DEFAULT_CHUNK_SIZE,
    overlap: int = _DEFAULT_CHUNK_OVERLAP,
) -> list[str]:
    """Split CMS text into fixed-size overlapping chunks."""

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
    tenant_id: UUID | int | str,
    query: str,
    top_k: int = 5,
    session: AsyncSession | None = None,
) -> list[dict[str, object]]:
    """Retrieve tenant-scoped chunks from indexed CMS content."""

    cleaned_query = query.strip()
    if session is None or not cleaned_query:
        return []

    safe_top_k = max(1, min(top_k, _MAX_TOP_K))
    query_terms = _expanded_query_terms(cleaned_query)
    if not query_terms:
        return []

    candidates = await _retrieve_indexed_candidates(
        session=session,
        tenant_id=tenant_id,
        query_terms=query_terms,
        raw_query=cleaned_query,
    )
    if not candidates:
        candidates = await _retrieve_cms_fallback_candidates(
            session=session,
            tenant_id=tenant_id,
            query_terms=query_terms,
            raw_query=cleaned_query,
        )

    ranked = sorted(candidates, key=lambda item: item.score, reverse=True)[:safe_top_k]
    return [asdict(chunk) for chunk in ranked]


async def _retrieve_indexed_candidates(
    *,
    session: AsyncSession,
    tenant_id: UUID | int | str,
    query_terms: set[str],
    raw_query: str,
) -> list[RagChunk]:
    try:
        async with session.begin_nested():
            result = await session.execute(
                _INDEXED_CHUNKS_SQL,
                {"tenant_id": str(tenant_id)},
            )
            rows = result.mappings().all()
    except (SQLAlchemyError, ValueError):
        _log.warning("rag_chunks retrieval failed; falling back to cms_pages", exc_info=True)
        return []

    candidates: list[RagChunk] = []
    for row in rows:
        text = str(row["text"] or "")
        score = _score_chunk(query_terms, raw_query, text)
        if score <= 0:
            continue

        metadata = _metadata_dict(row.get("metadata_json"))
        source_title = (
            str(metadata.get("source_title") or row["source_title"] or "CMS content")
        )
        source_url = metadata.get("source_url") or row.get("source_url")

        candidates.append(
            RagChunk(
                chunk_id=str(row["chunk_id"]),
                tenant_id=str(row["tenant_id"]),
                page_id=str(row["page_id"]),
                text=text,
                score=score,
                source_title=source_title,
                source_type=str(metadata.get("source_type") or "cms_page"),
                source_url=str(source_url) if source_url else None,
            )
        )

    return candidates


async def _retrieve_cms_fallback_candidates(
    *,
    session: AsyncSession,
    tenant_id: UUID | int | str,
    query_terms: set[str],
    raw_query: str,
) -> list[RagChunk]:
    result = await session.execute(
        select(CmsPage)
        .where(CmsPage.tenant_id == tenant_id, CmsPage.status == "published")
        .order_by(CmsPage.id.asc())
    )
    pages = list(result.scalars().all())

    candidates: list[RagChunk] = []
    for page in pages:
        title = str(getattr(page, "title", "CMS content") or "CMS content")
        body = str(getattr(page, "body", "") or "")
        source_url = getattr(page, "source_url", None)

        for index, chunk in enumerate(chunk_text(body)):
            score = _score_chunk(query_terms, raw_query, chunk)
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
                    source_url=str(source_url) if source_url else None,
                )
            )

    return candidates


def _tokenize(text: str) -> set[str]:
    """Tokenize a query/chunk for lightweight lexical matching."""

    return {
        token
        for token in re.findall(r"[a-zA-Z0-9]+", text.lower())
        if len(token) > 2
    }


def _expanded_query_terms(query: str) -> set[str]:
    """Tokenize query and add deterministic aliases for the local RAG baseline."""

    terms = _tokenize(query)
    lowered = query.lower()

    if "membership" in lowered or "cost" in lowered or "price" in lowered:
        terms.update({"membership", "memberships", "month", "dollars", "pricing"})

    if "open" in lowered or "saturday" in lowered or "hours" in lowered:
        terms.update({"open", "saturday", "hours"})

    if "located" in lowered or "where" in lowered or "location" in lowered:
        terms.update({"located", "location", "station", "library"})

    if "cancellation" in lowered or "cancel" in lowered:
        terms.update({"cancellation", "policy", "hours"})

    return terms


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


def _metadata_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


_INDEXED_CHUNKS_SQL = sql_text(
    """
    SELECT
        CAST(rc.id AS text) AS chunk_id,
        CAST(rc.tenant_id AS text) AS tenant_id,
        CAST(rc.page_id AS text) AS page_id,
        rc.text AS text,
        rc.metadata_json AS metadata_json,
        cp.title AS source_title,
        cp.source_url AS source_url
    FROM rag_chunks rc
    JOIN cms_pages cp
      ON cp.id = rc.page_id
     AND cp.tenant_id = rc.tenant_id
    WHERE rc.tenant_id = CAST(:tenant_id AS uuid)
      AND cp.tenant_id = CAST(:tenant_id AS uuid)
      AND cp.status = 'published'
    ORDER BY rc.page_id ASC, rc.chunk_index ASC
    """
)
