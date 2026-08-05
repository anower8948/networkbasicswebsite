"""Async engine, session factory, and the FastAPI session dependency."""

from __future__ import annotations

from collections.abc import AsyncGenerator
from typing import Any

from sqlalchemy import event
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.core.config import settings


def _engine_kwargs() -> dict[str, Any]:
    if settings.is_sqlite:
        # SQLite ignores pool sizing; passing pool args raises with aiosqlite.
        return {}
    return {
        "pool_size": settings.DB_POOL_SIZE,
        "max_overflow": settings.DB_MAX_OVERFLOW,
        "pool_pre_ping": True,  # recycle connections dropped by Azure's idle timeout
        "pool_recycle": 1800,
    }


engine: AsyncEngine = create_async_engine(
    settings.DATABASE_URL,
    echo=settings.DB_ECHO,
    future=True,
    **_engine_kwargs(),
)

if settings.is_sqlite:

    @event.listens_for(engine.sync_engine, "connect")
    def _configure_sqlite(dbapi_connection: Any, _record: Any) -> None:
        """SQLite defaults are unsafe for our access patterns.

        Foreign keys are off by default (silently breaking every FK in the
        schema) and the rollback journal serialises readers against writers.
        WAL plus enforced foreign keys makes dev behave like production.
        """
        cursor = dbapi_connection.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.close()


SessionFactory: async_sessionmaker[AsyncSession] = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,  # allow reading attributes after commit in responses
    autoflush=False,
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped session.

    The session is rolled back and closed automatically. Endpoints and services
    commit explicitly; anything that escapes as an exception leaves no partial
    writes behind.
    """
    async with SessionFactory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engine() -> None:
    """Close all pooled connections during application shutdown."""
    await engine.dispose()
