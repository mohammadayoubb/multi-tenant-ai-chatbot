# Owner: Amer
"""Integration tests for the SqlWidgetRepository.

Runs against the docker-compose Postgres + the widget_configs table from
migration 0004. Skipped unless `CONCIERGE_INTEGRATION_DB_URL` is set, so the
suite stays runnable on machines without docker. The CI job that runs
`docker compose up` should export it.

Local invocation:
    export CONCIERGE_INTEGRATION_DB_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/concierge
    pytest tests/integration/test_sql_widget_repo.py
"""

from __future__ import annotations

import os
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import delete, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.db.models import Tenant, WidgetConfig
from app.repositories.widget_repo import SqlWidgetRepository

_DB_URL = os.getenv("CONCIERGE_INTEGRATION_DB_URL")

pytestmark = pytest.mark.skipif(
    not _DB_URL,
    reason="set CONCIERGE_INTEGRATION_DB_URL to a running Postgres to enable",
)


@pytest_asyncio.fixture
async def session() -> AsyncSession:
    engine = create_async_engine(_DB_URL or "", pool_pre_ping=True)
    maker = async_sessionmaker(engine, expire_on_commit=False)
    async with maker() as sess:
        yield sess
    await engine.dispose()


@pytest_asyncio.fixture
async def seeded(session: AsyncSession):
    """One tenant + one widget_config row, cleaned up after the test."""
    tenant_id = uuid4()
    widget_id = uuid4()
    tenant = Tenant(
        id=tenant_id,
        name=f"SQLRepoTest-{tenant_id.hex[:8]}",
        slug=f"sqlrepotest-{tenant_id.hex[:8]}",
        status="active",
        plan="starter",
    )
    config = WidgetConfig(
        id=uuid4(),
        tenant_id=tenant_id,
        widget_id=widget_id,
        allowed_origins_json=["https://customer-site.example", "http://localhost:5173"],
        theme_json={},
        greeting="",
        enabled=True,
    )
    session.add_all([tenant, config])
    await session.commit()

    yield tenant_id, widget_id

    # Cleanup: explicit delete inside a tenant context so RLS doesn't block.
    await session.execute(
        text("SELECT set_config('app.tenant_id', :tid, true)"),
        {"tid": str(tenant_id)},
    )
    await session.execute(delete(WidgetConfig).where(WidgetConfig.tenant_id == tenant_id))
    await session.execute(text("SELECT set_config('app.tenant_id', '', true)"))
    await session.execute(delete(Tenant).where(Tenant.id == tenant_id))
    await session.commit()


@pytest.mark.asyncio
async def test_sql_repo_get_by_widget_id_returns_domain_row(session, seeded) -> None:
    tenant_id, widget_id = seeded
    repo = SqlWidgetRepository(session)
    row = await repo.get_by_widget_id(widget_id)
    assert row is not None
    assert row.tenant_id == tenant_id
    assert row.widget_id == widget_id
    assert row.enabled is True
    assert row.tenant_status == "active"
    assert "https://customer-site.example" in row.allowed_origins


@pytest.mark.asyncio
async def test_sql_repo_get_by_widget_id_unknown_returns_none(session) -> None:
    repo = SqlWidgetRepository(session)
    assert await repo.get_by_widget_id(uuid4()) is None


@pytest.mark.asyncio
async def test_sql_repo_get_by_tenant_id_returns_domain_row(session, seeded) -> None:
    tenant_id, widget_id = seeded
    repo = SqlWidgetRepository(session)
    row = await repo.get_by_tenant_id(tenant_id)
    assert row is not None
    assert row.widget_id == widget_id


@pytest.mark.asyncio
async def test_sql_repo_update_replaces_allowed_origins(session, seeded) -> None:
    tenant_id, widget_id = seeded
    repo = SqlWidgetRepository(session)
    updated = await repo.update_by_tenant_id(
        tenant_id,
        allowed_origins=["https://acme.example"],
        enabled=True,
        theme_json={"accent": "#2563eb"},
        greeting="Hello!",
    )
    assert updated is not None
    assert updated.allowed_origins == ["https://acme.example"]
    assert updated.greeting == "Hello!"
    assert updated.theme_json == {"accent": "#2563eb"}


@pytest.mark.asyncio
async def test_sql_repo_update_unknown_tenant_returns_none(session) -> None:
    repo = SqlWidgetRepository(session)
    result = await repo.update_by_tenant_id(
        uuid4(),
        allowed_origins=["https://nobody.example"],
        enabled=True,
        theme_json=None,
        greeting=None,
    )
    assert result is None
