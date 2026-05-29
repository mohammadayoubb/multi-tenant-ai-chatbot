from __future__ import annotations

import json
from uuid import UUID, uuid4

import pytest

from app.rag.ingest import (
    EMBEDDING_DIM,
    deterministic_embedding,
    embed_cms_page,
    prepare_cms_page_chunks,
    sync_cms_page_index,
)


class _FakeSession:
    def __init__(self) -> None:
        self.executed: list[dict[str, object]] = []
        self.flushes = 0

    async def execute(self, _statement, params):
        self.executed.append(dict(params))

    async def flush(self) -> None:
        self.flushes += 1


def test_prepare_cms_page_chunks_is_stable_and_tenant_scoped() -> None:
    tenant_id = uuid4()
    page_id = uuid4()

    chunks_a = prepare_cms_page_chunks(
        tenant_id=tenant_id,
        page_id=page_id,
        text="  Pricing   starts at 40 dollars per month. ",
        source_title="Pricing",
    )
    chunks_b = prepare_cms_page_chunks(
        tenant_id=tenant_id,
        page_id=page_id,
        text="Pricing starts at 40 dollars per month.",
        source_title="Pricing",
    )

    assert len(chunks_a) == 1
    assert chunks_a[0].chunk_id == chunks_b[0].chunk_id
    assert UUID(chunks_a[0].chunk_id)
    assert chunks_a[0].tenant_id == tenant_id
    assert chunks_a[0].page_id == page_id
    assert chunks_a[0].source_type == "cms_page"


def test_deterministic_embedding_has_expected_dimension() -> None:
    first = deterministic_embedding("alpha cookies pricing")
    second = deterministic_embedding("alpha cookies pricing")

    assert len(first) == EMBEDDING_DIM
    assert first == second
    assert any(value != 0 for value in first)


@pytest.mark.asyncio
async def test_embed_cms_page_draft_without_session_returns_no_chunks() -> None:
    chunks = await embed_cms_page(
        tenant_id=1,
        page_id=10,
        text="Hidden draft content",
        status="draft",
    )

    assert chunks == []


@pytest.mark.asyncio
async def test_sync_cms_page_index_deletes_then_inserts_published_chunks() -> None:
    session = _FakeSession()
    tenant_id = uuid4()
    page_id = uuid4()

    chunks = await sync_cms_page_index(
        session,  # type: ignore[arg-type]
        tenant_id=tenant_id,
        page_id=page_id,
        text="Alpha cookies are available Monday through Friday.",
        source_title="Opening Hours",
        source_url="https://example.test/opening-hours",
        status="published",
    )

    assert len(chunks) == 1
    assert len(session.executed) == 2
    assert session.executed[0] == {"tenant_id": str(tenant_id), "page_id": str(page_id)}

    inserted = session.executed[1]
    assert inserted["id"] == chunks[0].chunk_id
    assert inserted["tenant_id"] == str(tenant_id)
    assert inserted["page_id"] == str(page_id)
    assert str(inserted["embedding"]).startswith("[")

    metadata = json.loads(str(inserted["metadata_json"]))
    assert metadata["source_title"] == "Opening Hours"
    assert metadata["source_url"] == "https://example.test/opening-hours"
    assert session.flushes == 1


@pytest.mark.asyncio
async def test_sync_cms_page_index_deletes_archived_page_without_insert() -> None:
    session = _FakeSession()

    chunks = await sync_cms_page_index(
        session,  # type: ignore[arg-type]
        tenant_id=uuid4(),
        page_id=uuid4(),
        text="Archived content",
        status="archived",
    )

    assert chunks == []
    assert len(session.executed) == 1
    assert session.flushes == 1
