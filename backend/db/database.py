from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import Session, sessionmaker

from backend.config import settings

# Async engine (for FastAPI endpoints)
engine = create_async_engine(settings.database_url, echo=False)
async_session = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

# Sync engine (for background simulation threads)
_sync_url = settings.database_url.replace("sqlite+aiosqlite", "sqlite")
sync_engine = create_engine(_sync_url, echo=False)
SyncSession = sessionmaker(sync_engine, class_=Session)


async def get_db() -> AsyncSession:
    async with async_session() as session:
        yield session


async def init_db():
    from backend.db.models import Base

    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
