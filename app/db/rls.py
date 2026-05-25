# Owner: Hiba
"""Row-Level Security helpers.

This file will contain helpers to set and reset the Postgres tenant context.
"""

from sqlalchemy.ext.asyncio import AsyncSession


async def set_tenant_context(session: AsyncSession, tenant_id: int) -> None:
    """Set tenant context for the current database session."""
    await session.execute("SELECT set_config('app.tenant_id', :tenant_id, true)", {"tenant_id": str(tenant_id)})


async def reset_tenant_context(session: AsyncSession) -> None:
    """Reset tenant context to avoid leaking tenant_id across pooled connections."""
    await session.execute("SELECT set_config('app.tenant_id', '', true)")
