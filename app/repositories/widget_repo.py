# Owner: Amer
# Schema-touching code flagged for Hiba review (CONTRACT.md §8 widget_configs).
"""Widget configuration repository.

This is the one acceptable read path where `tenant_id` flows OUT of the
lookup rather than IN — the entire purpose of the lookup is to discover
which tenant owns a widget (Constitution Principle I, data-model.md §1).

The InMemoryWidgetRepository is a documented temporary affordance
(plan.md Complexity Tracking row 2). It will be deleted in the PR that
introduces the SQL adapter against Hiba's widget_configs migration.
"""

from __future__ import annotations

from typing import Protocol
from uuid import UUID

from app.domain.widget import WidgetConfigDomain
from app.services.widget_settings import widget_settings


class WidgetRepository(Protocol):
    async def get_by_widget_id(self, widget_id: UUID) -> WidgetConfigDomain | None:
        """Return the widget configuration row joined with the owning tenant's status.

        Returns None if no row matches. Does not take a tenant_id argument —
        see module docstring and data-model.md §1.
        """
        ...


class InMemoryWidgetRepository:
    """In-memory fixture-backed implementation. Temporary; see module docstring."""

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
                ],
                enabled=True,
                tenant_status="active",
            ),
        }

    async def get_by_widget_id(self, widget_id: UUID) -> WidgetConfigDomain | None:
        return self._rows.get(widget_id)

    # Test affordances. Not part of the WidgetRepository Protocol.
    def upsert(self, row: WidgetConfigDomain) -> None:
        self._rows[row.widget_id] = row

    def clear(self) -> None:
        self._rows.clear()


def get_widget_repository() -> WidgetRepository:
    """Factory returning the configured backend (memory|sql)."""
    backend = widget_settings().widget_repo_backend
    if backend == "memory":
        return InMemoryWidgetRepository()
    if backend == "sql":
        raise NotImplementedError(
            "SQL widget repository pending Hiba's widget_configs migration. "
            "Use WIDGET_REPO_BACKEND=memory until that lands."
        )
    raise ValueError(f"Unknown WIDGET_REPO_BACKEND: {backend}")
