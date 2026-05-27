# Owner: Nasser
"""CMS-to-embedding ingestion pipeline."""

from __future__ import annotations

from dataclasses import dataclass

from app.rag.retriever import chunk_text


@dataclass(frozen=True)
class PreparedChunk:
    """A tenant-scoped chunk ready for hosted embedding + pgvector insert."""

    tenant_id: int
    page_id: int
    chunk_index: int
    text: str


async def embed_cms_page(tenant_id: int, page_id: int, text: str) -> list[PreparedChunk]:
    """Prepare one CMS page for embedding.

    The hosted embedding call / pgvector insert can be wired later; this keeps
    the tenant-scoped chunking contract concrete and testable now.
    """

    return [
        PreparedChunk(
            tenant_id=tenant_id,
            page_id=page_id,
            chunk_index=index,
            text=chunk,
        )
        for index, chunk in enumerate(chunk_text(text))
    ]
