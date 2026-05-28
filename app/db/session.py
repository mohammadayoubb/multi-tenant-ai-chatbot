# Owner: Hiba
"""Database engine and session lifecycle."""

from collections.abc import AsyncGenerator
from functools import lru_cache

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config import get_app_secrets


@lru_cache(maxsize=1)
def get_engine() -> AsyncEngine:
    """Create the async engine from Vault-resolved settings."""
    secrets = get_app_secrets()
    return create_async_engine(secrets.database_url, pool_pre_ping=True)


@lru_cache(maxsize=1)
def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    """Return cached async session factory."""
    return async_sessionmaker(get_engine(), expire_on_commit=False)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield an async database session with commit/rollback handling."""
    async with get_sessionmaker()() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
