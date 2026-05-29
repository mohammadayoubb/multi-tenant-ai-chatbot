# Owner: Nasser
"""CMS-to-RAG ingestion pipeline.

CMS pages are the tenant-owned knowledge source for chat answers. This module
normalizes page text, chunks it, creates deterministic local embeddings, and
writes the result to the tenant-scoped ``rag_chunks`` table.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import uuid
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import AsyncSession

from app.rag.retriever import chunk_text

EMBEDDING_DIM = 1536
SOURCE_TYPE = "cms_page"


@dataclass(frozen=True)
class PreparedChunk:
    """A tenant-scoped chunk ready for pgvector insertion."""

    chunk_id: str
    tenant_id: UUID | int | str
    page_id: UUID | int | str
    chunk_index: int
    text: str
    source_title: str
    source_type: str
    content_sha256: str
    created_at: str
    source_url: str | None = None

    def to_record(self) -> dict[str, object]:
        """Return a dictionary suitable for tests, logs, or repository adapters."""

        return asdict(self)


async def embed_cms_page(
    tenant_id: UUID | int | str,
    page_id: UUID | int | str,
    text: str,
    source_title: str = "CMS content",
    *,
    source_url: str | None = None,
    session: AsyncSession | None = None,
    status: str = "published",
) -> list[PreparedChunk]:
    """Prepare or index one CMS page.

    When ``session`` is supplied, chunks are written to ``rag_chunks``. Without a
    session this keeps the old test-friendly behavior and only returns prepared
    records.
    """

    if session is None:
        if status != "published":
            return []
        return prepare_cms_page_chunks(
            tenant_id=tenant_id,
            page_id=page_id,
            text=text,
            source_title=source_title,
            source_url=source_url,
        )

    return await sync_cms_page_index(
        session,
        tenant_id=tenant_id,
        page_id=page_id,
        text=text,
        source_title=source_title,
        source_url=source_url,
        status=status,
    )


def prepare_cms_page_chunks(
    *,
    tenant_id: UUID | int | str,
    page_id: UUID | int | str,
    text: str,
    source_title: str = "CMS content",
    source_url: str | None = None,
) -> list[PreparedChunk]:
    """Normalize and chunk one CMS page without touching the database."""

    cleaned_text = _normalize_text(text)
    if not cleaned_text:
        return []

    chunks = chunk_text(cleaned_text)
    created_at = datetime.now(tz=UTC).isoformat()
    safe_title = source_title.strip() or "CMS content"

    return [
        PreparedChunk(
            chunk_id=str(
                _stable_chunk_uuid(
                    tenant_id=tenant_id,
                    page_id=page_id,
                    chunk_index=index,
                    text=chunk,
                )
            ),
            tenant_id=tenant_id,
            page_id=page_id,
            chunk_index=index,
            text=chunk,
            source_title=safe_title,
            source_type=SOURCE_TYPE,
            content_sha256=_sha256(chunk),
            created_at=created_at,
            source_url=source_url,
        )
        for index, chunk in enumerate(chunks)
    ]


async def sync_cms_page_index(
    session: AsyncSession | None,
    *,
    tenant_id: UUID | int | str,
    page_id: UUID | int | str,
    text: str,
    source_title: str = "CMS content",
    source_url: str | None = None,
    status: str = "published",
) -> list[PreparedChunk]:
    """Replace the stored RAG chunks for one CMS page.

    Draft and archived pages are removed from the RAG index so visitors only see
    published tenant content.
    """

    if session is None:
        return []

    await delete_cms_page_chunks(session, tenant_id=tenant_id, page_id=page_id)

    if status != "published":
        await session.flush()
        return []

    chunks = prepare_cms_page_chunks(
        tenant_id=tenant_id,
        page_id=page_id,
        text=text,
        source_title=source_title,
        source_url=source_url,
    )

    for chunk in chunks:
        await session.execute(
            _INSERT_CHUNK_SQL,
            {
                "id": chunk.chunk_id,
                "tenant_id": str(tenant_id),
                "page_id": str(page_id),
                "chunk_index": chunk.chunk_index,
                "text": chunk.text,
                "embedding": _embedding_literal(
                    deterministic_embedding(f"{chunk.source_title}\n{chunk.text}")
                ),
                "metadata_json": json.dumps(
                    {
                        "source_title": chunk.source_title,
                        "source_type": chunk.source_type,
                        "source_url": chunk.source_url,
                        "content_sha256": chunk.content_sha256,
                    }
                ),
            },
        )

    await session.flush()
    return chunks


async def delete_cms_page_chunks(
    session: AsyncSession | None,
    *,
    tenant_id: UUID | int | str,
    page_id: UUID | int | str,
) -> None:
    """Delete all RAG chunks for one tenant-scoped CMS page."""

    if session is None:
        return

    await session.execute(
        _DELETE_PAGE_CHUNKS_SQL,
        {"tenant_id": str(tenant_id), "page_id": str(page_id)},
    )


def deterministic_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """Return a deterministic hashed bag-of-words embedding.

    This keeps local Docker/demo RAG functional without a hosted embedding API.
    The storage contract remains pgvector-compatible, so a hosted model can
    replace this function later without changing CMS or retrieval call sites.
    """

    vector = [0.0] * dim
    for token in _tokens(text):
        digest = hashlib.sha256(token.encode("utf-8")).digest()
        bucket = int.from_bytes(digest[:4], "big") % dim
        sign = 1.0 if digest[4] % 2 == 0 else -1.0
        vector[bucket] += sign

    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [round(value / norm, 6) for value in vector]


def _normalize_text(text: str) -> str:
    """Normalize CMS body text before chunking."""

    return " ".join(text.split())


def _stable_chunk_uuid(
    *,
    tenant_id: UUID | int | str,
    page_id: UUID | int | str,
    chunk_index: int,
    text: str,
) -> UUID:
    """Create a stable UUID for repeatable ingestion."""

    return uuid.uuid5(
        uuid.NAMESPACE_URL,
        f"rag:{tenant_id}:{page_id}:{chunk_index}:{_sha256(text)}",
    )


def _sha256(value: str) -> str:
    """Return SHA-256 hex digest for content tracking."""

    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _tokens(text: str) -> list[str]:
    return re.findall(r"[a-zA-Z0-9]+", text.lower())


def _embedding_literal(values: list[float]) -> str:
    return "[" + ",".join(str(value) for value in values) + "]"


_DELETE_PAGE_CHUNKS_SQL = sql_text(
    """
    DELETE FROM rag_chunks
    WHERE tenant_id = CAST(:tenant_id AS uuid)
      AND page_id = CAST(:page_id AS uuid)
    """
)

_INSERT_CHUNK_SQL = sql_text(
    """
    INSERT INTO rag_chunks (
        id,
        tenant_id,
        page_id,
        chunk_index,
        text,
        embedding,
        metadata_json
    )
    VALUES (
        CAST(:id AS uuid),
        CAST(:tenant_id AS uuid),
        CAST(:page_id AS uuid),
        :chunk_index,
        :text,
        CAST(:embedding AS vector),
        CAST(:metadata_json AS jsonb)
    )
    """
)
