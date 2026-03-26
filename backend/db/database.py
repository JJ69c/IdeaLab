"""Database engine and session configuration.

Supports both PostgreSQL (production) and SQLite (dev fallback).
The async URL from config.py drives the async engine; the sync URL
is derived automatically for background simulation threads.

PostgreSQL: postgresql+asyncpg → postgresql+psycopg2  (sync)
SQLite:     sqlite+aiosqlite   → sqlite               (sync)
"""

from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import settings


def _derive_sync_url(async_url: str) -> str:
    """Convert an async database URL to its sync equivalent."""
    if "asyncpg" in async_url:
        return async_url.replace("postgresql+asyncpg", "postgresql+psycopg2")
    if "aiosqlite" in async_url:
        return async_url.replace("sqlite+aiosqlite", "sqlite")
    # Already a sync URL or unknown driver — return as-is
    return async_url


def _is_sqlite(url: str) -> bool:
    return url.startswith("sqlite")


# Async engine (for FastAPI endpoints)
_engine_kwargs: dict = {"echo": False}
if not _is_sqlite(settings.database_url):
    # PostgreSQL connection pool settings for concurrent access
    _engine_kwargs.update(pool_size=10, max_overflow=20)

engine = create_async_engine(settings.database_url, **_engine_kwargs)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine (for background simulation threads)
_sync_url = _derive_sync_url(settings.database_url)
_sync_kwargs: dict = {"echo": False}
if not _is_sqlite(_sync_url):
    _sync_kwargs.update(pool_size=5, max_overflow=10)

sync_engine = create_engine(_sync_url, **_sync_kwargs)
SyncSession = sessionmaker(sync_engine, class_=Session)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    """Run Alembic migrations to bring the database schema up to date.

    Alembic's command API is synchronous, so we run it in a thread
    to avoid blocking the async event loop during startup.
    """
    import asyncio

    def _run_migrations():
        from alembic import command
        from alembic.config import Config

        alembic_cfg = Config("alembic.ini")
        # Override the URL to match the app config (sync driver for Alembic)
        alembic_cfg.set_main_option("sqlalchemy.url", _sync_url)
        command.upgrade(alembic_cfg, "head")

    await asyncio.to_thread(_run_migrations)
