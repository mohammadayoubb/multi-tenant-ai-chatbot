# Owner: Amer
# Schema-touching code flagged for Hiba review (CONTRACT.md §8 widget_configs).
"""Widget configuration repository.

Two interchangeable backends behind one Protocol:

- `InMemoryWidgetRepository` — process-local dict, seeded with the demo widget
  fixture. Used by tests and by `WIDGET_REPO_BACKEND=memory`. State persists
  across requests via a module-level singleton (`_get_in_memory_repo`).
- `SqlWidgetRepository` — backs the `widget_configs` table added by migration
  `0004_contract_schema_parity.py`. Used by `WIDGET_REPO_BACKEND=sql`. Each
  request gets a fresh repo bound to the request's `AsyncSession`.

The `get_by_widget_id` lookup is the one legitimate read path where `tenant_id`
flows OUT (Constitution Principle I, feature-001 data-model.md §1) — it has to
work without tenant context because the visitor has no JWT yet. With the
default `postgres` superuser this is fine (superusers bypass RLS); for a
hardened deployment the connection role would switch to non-superuser and
this lookup would need a SECURITY DEFINER function. Documented for a future
hardening pass; out of scope for the current cut.

Every other read/write is explicitly scoped by `tenant_id` (CONTRACT.md §7).
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from fastapi import Depends
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import Tenant, WidgetConfig
from app.db.session import get_session
from app.domain.widget import WidgetConfigDomain
from app.services.widget_settings import widget_settings


class WidgetRepository(Protocol):
    async def get_by_widget_id(self, widget_id: UUID) -> WidgetConfigDomain | None:
        """Return the widget configuration row joined with the owning tenant's status.

        Returns None if no row matches. Does not take a tenant_id argument —
        see module docstring and feature-001 data-model.md §1.
        """
        ...

    async def get_by_tenant_id(self, tenant_id: UUID) -> WidgetConfigDomain | None:
        """Return the widget configuration row for the given tenant.

        Tenant-scoped read for the admin config endpoint (feature 004).
        Returns None if no row matches the tenant. Implementations MUST scope
        their query by tenant_id (Principle I).
        """
        ...

    async def update_by_tenant_id(
        self,
        tenant_id: UUID,
        *,
        allowed_origins: list[str],
        enabled: bool,
        theme_json: dict | None,
        greeting: str | None,
    ) -> WidgetConfigDomain | None:
        """Update the widget configuration row for the given tenant and return it.

        Returns None if no row exists for the tenant. Implementations MUST scope
        their UPDATE by tenant_id in the WHERE clause (Principle I).
        """
        ...


# ---------------------------------------------------------------------------
# In-memory backend (development / tests)
# ---------------------------------------------------------------------------


class InMemoryWidgetRepository:
    """In-memory fixture-backed implementation. Singleton across requests
    (see `_get_in_memory_repo`) so state survives the request lifecycle."""

    _FIXTURE_WIDGET_ID = UUID("9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d")
    _FIXTURE_TENANT_ID = UUID("11111111-1111-1111-1111-111111111111")
    _FIXTURE_ROW_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    def __init__(self) -> None:
        self._rows: dict[UUID, WidgetConfigDomain] = {
            self._FIXTURE_WIDGET_ID: WidgetConfigDomain(
                id=self._FIXTURE_ROW_ID,
                tenant_id=self._FIXTURE_TENANT_ID,
                widget_id=self._FIXTURE_WIDGET_ID,
                allowed_origins=[
                    "https://customer-site.example",
                    "http://localhost:5500",
                    "http://localhost:5173",
                ],
                enabled=True,
                tenant_status="active",
                theme_json=None,
                greeting=None,
            ),
        }

    async def get_by_widget_id(self, widget_id: UUID) -> WidgetConfigDomain | None:
        return self._rows.get(widget_id)

    async def get_by_tenant_id(self, tenant_id: UUID) -> WidgetConfigDomain | None:
        for row in self._rows.values():
            if row.tenant_id == tenant_id:
                return row
        return None

    async def update_by_tenant_id(
        self,
        tenant_id: UUID,
        *,
        allowed_origins: list[str],
        enabled: bool,
        theme_json: dict | None,
        greeting: str | None,
    ) -> WidgetConfigDomain | None:
        existing = await self.get_by_tenant_id(tenant_id)
        if existing is None:
            return None
        updated = existing.model_copy(
            update={
                "allowed_origins": list(allowed_origins),
                "enabled": enabled,
                "theme_json": theme_json,
                "greeting": greeting,
            }
        )
        self._rows[existing.widget_id] = updated
        return updated

    # Test affordances. Not part of the WidgetRepository Protocol.
    def upsert(self, row: WidgetConfigDomain) -> None:
        self._rows[row.widget_id] = row

    def clear(self) -> None:
        self._rows.clear()


# ---------------------------------------------------------------------------
# SQL backend (production)
# ---------------------------------------------------------------------------


class SqlWidgetRepository:
    """SQL implementation backed by the `widget_configs` table.

    Joins with `tenants` to populate `tenant_status` on the domain row — the
    domain model treats tenant status as part of the widget lookup because
    every place we read a widget config we also need to know whether the
    tenant is active (token issuance refuses suspended/erasing/erased tenants).
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_widget_id(self, widget_id: UUID) -> WidgetConfigDomain | None:
        result = await self._session.execute(
            select(WidgetConfig, Tenant.status.label("tenant_status"))
            .join(Tenant, Tenant.id == WidgetConfig.tenant_id)
            .where(WidgetConfig.widget_id == widget_id)
        )
        row = result.first()
        if row is None:
            return None
        return _to_domain(row[0], row.tenant_status)

    async def get_by_tenant_id(self, tenant_id: UUID) -> WidgetConfigDomain | None:
        result = await self._session.execute(
            select(WidgetConfig, Tenant.status.label("tenant_status"))
            .join(Tenant, Tenant.id == WidgetConfig.tenant_id)
            .where(WidgetConfig.tenant_id == tenant_id)
        )
        row = result.first()
        if row is None:
            return None
        return _to_domain(row[0], row.tenant_status)

    async def update_by_tenant_id(
        self,
        tenant_id: UUID,
        *,
        allowed_origins: list[str],
        enabled: bool,
        theme_json: dict | None,
        greeting: str | None,
    ) -> WidgetConfigDomain | None:
        # Tenant-scoped UPDATE (CONTRACT.md §7). The DB-level NOT NULL on
        # theme_json and greeting means we coerce None -> default at the
        # boundary; the domain model still treats both as nullable.
        result = await self._session.execute(
            update(WidgetConfig)
            .where(WidgetConfig.tenant_id == tenant_id)
            .values(
                allowed_origins_json=list(allowed_origins),
                enabled=enabled,
                theme_json=theme_json if theme_json is not None else {},
                greeting=greeting if greeting is not None else "",
            )
            .returning(WidgetConfig.id)
        )
        if result.first() is None:
            return None
        await self._session.flush()
        return await self.get_by_tenant_id(tenant_id)


def _to_domain(row: WidgetConfig, tenant_status: str) -> WidgetConfigDomain:
    """Map a SQL row + the joined tenant status into the domain model.

    Coerces NOT-NULL empty values (theme_json={}, greeting='') back to None
    so the domain layer can treat 'unset' uniformly across both backends.
    """
    theme = row.theme_json if row.theme_json else None
    greeting = row.greeting if row.greeting else None
    return WidgetConfigDomain(
        id=row.id,
        tenant_id=row.tenant_id,
        widget_id=row.widget_id,
        allowed_origins=list(row.allowed_origins_json or []),
        enabled=row.enabled,
        tenant_status=tenant_status,
        theme_json=theme,
        greeting=greeting,
    )


# ---------------------------------------------------------------------------
# Factory — FastAPI dep
# ---------------------------------------------------------------------------

# In-memory backend keeps state across requests via this singleton.
_in_memory_repo: InMemoryWidgetRepository | None = None


def _get_in_memory_repo() -> InMemoryWidgetRepository:
    global _in_memory_repo
    if _in_memory_repo is None:
        _in_memory_repo = InMemoryWidgetRepository()
    return _in_memory_repo


def reset_in_memory_repo() -> None:
    """Drop the in-memory singleton so the next caller sees a fresh fixture.

    Used by tests that want a known-clean state without going through the
    Protocol's clear()/upsert() helpers.
    """
    global _in_memory_repo
    _in_memory_repo = None


def get_widget_repository(
    session: AsyncSession = Depends(get_session),
) -> WidgetRepository:
    """Factory returning the configured backend (memory|sql).

    Used as a FastAPI dependency so the SQL backend can be bound to the
    request-scoped session. The in-memory backend ignores the session and
    returns the module-level singleton.
    """
    backend = widget_settings().widget_repo_backend
    if backend == "memory":
        return _get_in_memory_repo()
    if backend == "sql":
        return SqlWidgetRepository(session)
    raise ValueError(f"Unknown WIDGET_REPO_BACKEND: {backend}")
