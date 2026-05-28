# Owner: Amer
"""Seed one widget_configs row for a tenant.

Usage:
    python -m scripts.seed_widget_config \
        --tenant-id 11111111-1111-1111-1111-111111111111 \
        --widget-id 9a7e3a3a-1a8d-4f3a-9f06-2e2b9a8b1c6d \
        --origin https://customer-site.example \
        --origin http://localhost:5173

Idempotent: if a widget_configs row already exists for the tenant_id, the
script prints the existing widget_id and exits 0. This lets `docker compose
up` re-run the bootstrap without producing duplicate rows or crashing.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys
from uuid import UUID, uuid4

from sqlalchemy import select

from app.db.models import WidgetConfig
from app.db.session import get_sessionmaker

LOGGER = logging.getLogger(__name__)


async def seed_widget_config(
    *,
    tenant_id: UUID,
    widget_id: UUID,
    allowed_origins: list[str],
    enabled: bool = True,
    greeting: str = "",
) -> tuple[UUID, bool]:
    """Insert a widget_configs row. Returns (widget_id, created)."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        existing = await session.execute(
            select(WidgetConfig).where(WidgetConfig.tenant_id == tenant_id)
        )
        row = existing.scalar_one_or_none()
        if row is not None:
            return row.widget_id, False

        try:
            row = WidgetConfig(
                id=uuid4(),
                tenant_id=tenant_id,
                widget_id=widget_id,
                allowed_origins_json=allowed_origins,
                theme_json={},
                greeting=greeting,
                enabled=enabled,
            )
            session.add(row)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return widget_id, True


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Seed a widget_configs row for a tenant."
    )
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument("--widget-id", required=True, type=UUID)
    parser.add_argument(
        "--origin",
        action="append",
        default=[],
        help="Allowed origin (repeat for multiple).",
    )
    parser.add_argument("--greeting", default="")
    parser.add_argument(
        "--disabled", action="store_true", help="Create the row with enabled=false."
    )
    args = parser.parse_args()

    if not args.origin:
        sys.stderr.write("error: at least one --origin is required\n")
        sys.exit(2)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    widget_id, created = asyncio.run(
        seed_widget_config(
            tenant_id=args.tenant_id,
            widget_id=args.widget_id,
            allowed_origins=args.origin,
            enabled=not args.disabled,
            greeting=args.greeting,
        )
    )
    state = "created" if created else "already existed"
    LOGGER.info("widget_config %s %s for tenant %s", widget_id, state, args.tenant_id)


if __name__ == "__main__":
    main()
