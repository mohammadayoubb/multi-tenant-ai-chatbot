# Owner: Amer
"""Admin user repository.

The `get_by_email` lookup runs BEFORE the JWT exists, so the login service
uses a session without tenant context set (the RLS policy would otherwise
reject the row). All other reads must come from request-scoped sessions where
`set_tenant_context` has already been called by the route layer.
"""

from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import AdminUser


class AdminUserRepository:
    """SQL operations for admin_users."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_email(self, email: str) -> AdminUser | None:
        """Lookup one admin user by email. Used by login (pre-tenant-context)."""
        result = await self._session.execute(
            select(AdminUser).where(AdminUser.email == email)
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        *,
        tenant_id: UUID,
        email: str,
        password_hash: str,
        role: str = "tenant_admin",
    ) -> AdminUser:
        """Insert a new admin user (called by the seed script)."""
        user = AdminUser(
            tenant_id=tenant_id,
            email=email,
            password_hash=password_hash,
            role=role,
        )
        self._session.add(user)
        await self._session.flush()
        return user

    async def get_by_id(self, user_id: UUID) -> AdminUser | None:
        """Lookup one admin user by id. Used by the escalations assignee check."""
        result = await self._session.execute(
            select(AdminUser).where(AdminUser.id == user_id)
        )
        return result.scalar_one_or_none()

    async def list_by_tenant(self, tenant_id: UUID) -> list[AdminUser]:
        """List active tenant_admin/tenant_manager users for one tenant.

        Used by the escalations assignee dropdown — only active users are
        eligible to be assigned. Cross-tenant scoping is enforced at the
        route layer.
        """
        result = await self._session.execute(
            select(AdminUser)
            .where(
                AdminUser.tenant_id == tenant_id,
                AdminUser.status == "active",
                AdminUser.role.in_(("tenant_admin", "tenant_manager")),
            )
            .order_by(AdminUser.email)
        )
        return list(result.scalars().all())
