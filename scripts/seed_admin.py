# Owner: Amer
"""Seed one tenant-admin user.

Usage:
    python -m scripts.seed_admin \
        --email admin@acme.example \
        --password 's3cret' \
        --tenant-id 11111111-1111-1111-1111-111111111111

The password may also come from the ADMIN_SEED_PASSWORD env var so it never
shows up in shell history. Email is unique; re-running with an existing email
is a no-op (returns the existing id) so the script is idempotent in CI/dev
provisioning.
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from uuid import UUID

from app.db.session import get_sessionmaker
from app.infra.password import hash_password
from app.repositories.admin_user_repo import AdminUserRepository

LOGGER = logging.getLogger(__name__)


async def seed_admin(
    *,
    email: str,
    password: str,
    tenant_id: UUID,
    role: str = "tenant_admin",
) -> tuple[UUID, bool]:
    """Create or no-op an admin user. Returns (user_id, created)."""
    sessionmaker = get_sessionmaker()
    async with sessionmaker() as session:
        repo = AdminUserRepository(session)
        existing = await repo.get_by_email(email)
        if existing is not None:
            return existing.id, False
        try:
            user = await repo.create(
                tenant_id=tenant_id,
                email=email,
                password_hash=hash_password(password),
                role=role,
            )
            await session.commit()
        except Exception:
            await session.rollback()
            raise
    return user.id, True


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed a tenant-admin user.")
    parser.add_argument("--email", required=True)
    parser.add_argument(
        "--password",
        default=None,
        help="Plaintext password. Defaults to $ADMIN_SEED_PASSWORD.",
    )
    parser.add_argument("--tenant-id", required=True, type=UUID)
    parser.add_argument(
        "--role",
        default="tenant_admin",
        choices=["tenant_admin", "tenant_manager"],
    )
    args = parser.parse_args()

    password = args.password or os.environ.get("ADMIN_SEED_PASSWORD")
    if not password:
        sys.stderr.write(
            "error: password required (pass --password or set ADMIN_SEED_PASSWORD)\n"
        )
        sys.exit(2)

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    user_id, created = asyncio.run(
        seed_admin(
            email=args.email,
            password=password,
            tenant_id=args.tenant_id,
            role=args.role,
        )
    )
    state = "created" if created else "already existed"
    LOGGER.info("admin %s %s (id=%s)", args.email, state, user_id)


if __name__ == "__main__":
    main()
