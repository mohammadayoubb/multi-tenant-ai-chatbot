# Owner: Nasser
"""CMS-to-embedding ingestion pipeline.

This module prepares tenant CMS content for RAG.

Current implementation:
- cleans CMS text
- splits text into overlapping chunks
- preserves tenant_id and page_id
- creates stable chunk IDs
- returns embedding-ready chunk records

Later implementation:
- call hosted embedding API
- insert chunk text + vector into pgvector
- keep tenant_id on every vector row
"""

from __future__ import annotations

import hashlib
from dataclasses import asdict, dataclass
from datetime import UTC, datetime

from app.rag.retriever import chunk_text


@dataclass(frozen=True)
class PreparedChunk:
    """A tenant-scoped chunk ready for hosted embedding + pgvector insert."""

    chunk_id: str
    tenant_id: int
    page_id: int
    chunk_index: int
    text: str
    source_title: str
    source_type: str
    content_sha256: str
    created_at: str

    def to_record(self) -> dict[str, object]:
        """Return a dictionary suitable for repository/embedding pipeline use."""

        return asdict(self)


async def embed_cms_page(
    tenant_id: int,
    page_id: int,
    text: str,
    source_title: str = "CMS content",
) -> list[PreparedChunk]:
    """Prepare one CMS page for hosted embedding and pgvector insertion.

    The hosted embedding call and pgvector insert can be wired later. This
    function keeps the tenant-scoped chunking contract concrete and testable now.
    """

    cleaned_text = _normalize_text(text)
    if not cleaned_text:
        return []

    chunks = chunk_text(cleaned_text)
    created_at = datetime.now(tz=UTC).isoformat()

    return [
        PreparedChunk(
            chunk_id=_stable_chunk_id(
                tenant_id=tenant_id,
                page_id=page_id,
                chunk_index=index,
                text=chunk,
            ),
            tenant_id=tenant_id,
            page_id=page_id,
            chunk_index=index,
            text=chunk,
            source_title=source_title.strip() or "CMS content",
            source_type="cms_page",
            content_sha256=_sha256(chunk),
            created_at=created_at,
        )
        for index, chunk in enumerate(chunks)
    ]


def _normalize_text(text: str) -> str:
    """Normalize CMS body text before chunking."""

    return " ".join(text.split())


def _stable_chunk_id(
    tenant_id: int,
    page_id: int,
    chunk_index: int,
    text: str,
) -> str:
    """Create a stable chunk ID for repeatable ingestion."""

    digest = _sha256(f"{tenant_id}:{page_id}:{chunk_index}:{text}")[:16]
    return f"tenant-{tenant_id}:page-{page_id}:chunk-{chunk_index}:{digest}"


def _sha256(value: str) -> str:
    """Return SHA-256 hex digest for content tracking."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()