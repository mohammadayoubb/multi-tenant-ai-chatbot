# Owner: Hiba
"""Seed demo tenants for the Friday demo."""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
import logging
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_sessionmaker
from app.domain.tenant import PlatformRole
from app.repositories.tenant_repo import TenantRepository
from app.services.tenant_service import TenantService

LOGGER = logging.getLogger(__name__)

DEMO_TENANT_NAMES = ("Tenant A", "Tenant B")


@dataclass(frozen=True)
class DemoRateLimitSeed:
    """Default rate-limit settings for demo tenants."""

    action: str
    limit_count: int
    window_seconds: int


@dataclass(frozen=True)
class SeededTenant:
    """Summary of one seeded tenant."""

    name: str
    tenant_id: UUID
    created: bool


DEFAULT_RATE_LIMITS = (
    DemoRateLimitSeed(action="chat", limit_count=100, window_seconds=60),
    DemoRateLimitSeed(action="rag", limit_count=60, window_seconds=60),
    DemoRateLimitSeed(action="agent", limit_count=30, window_seconds=60),
)


async def seed_demo_tenants(actor_id: str = "seed:hiba") -> list[SeededTenant]:
    """Create demo tenants and default rate limits if needed."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        try:
            seeded = await seed_demo_tenants_with_session(session, actor_id=actor_id)
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return seeded


async def seed_demo_tenants_with_session(
    session: AsyncSession,
    actor_id: str = "seed:hiba",
) -> list[SeededTenant]:
    """Seed demo tenants using an existing database session."""
    repo = TenantRepository(session)
    service = TenantService(repo)
    seeded: list[SeededTenant] = []

    for name in DEMO_TENANT_NAMES:
        tenant = await repo.get_by_name(name)
        created = tenant is None
        if tenant is None:
            tenant_domain = await service.provision_tenant(
                name=name,
                actor_role=PlatformRole.TENANT_MANAGER,
                actor_id=actor_id,
            )
            tenant_id = tenant_domain.id
        else:
            tenant_id = tenant.id

        for rate_limit in DEFAULT_RATE_LIMITS:
            await repo.upsert_rate_limit(
                tenant_id=tenant_id,
                action=rate_limit.action,
                limit_count=rate_limit.limit_count,
                window_seconds=rate_limit.window_seconds,
            )

        seeded.append(SeededTenant(name=name, tenant_id=tenant_id, created=created))

    return seeded


def main() -> None:
    """Seed Tenant A and Tenant B."""
    parser = argparse.ArgumentParser(description="Seed demo tenants and default rate limits.")
    parser.add_argument("--actor-id", default="seed:hiba")
    args = parser.parse_args()

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    seeded = asyncio.run(seed_demo_tenants(actor_id=args.actor_id))
    for tenant in seeded:
        state = "created" if tenant.created else "already existed"
        LOGGER.info("%s %s (%s)", tenant.name, state, tenant.tenant_id)


if __name__ == "__main__":
    main()
