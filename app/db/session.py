import asyncio
import itertools
import logging
from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.config import settings

logger = logging.getLogger(__name__)

# --- Primary (write) engine ---
_primary_engine = create_async_engine(
    settings.POSTGRES_PRIMARY_URL,
    echo=False,
    pool_size=20,
    max_overflow=10,
    pool_pre_ping=True,
)

_primary_session_factory = async_sessionmaker(
    bind=_primary_engine,
    class_=AsyncSession,
    expire_on_commit=False,
)

# --- Replica engines (read) ---
_replica_engines = {
    settings.POSTGRES_REPLICA1_URL: create_async_engine(
        settings.POSTGRES_REPLICA1_URL,
        echo=False,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
    ),
    settings.POSTGRES_REPLICA2_URL: create_async_engine(
        settings.POSTGRES_REPLICA2_URL,
        echo=False,
        pool_size=20,
        max_overflow=10,
        pool_pre_ping=True,
    ),
}

_replica_urls = [settings.POSTGRES_REPLICA1_URL, settings.POSTGRES_REPLICA2_URL]
_replica_cycle = itertools.cycle(_replica_urls)
_replica_lock = asyncio.Lock()


async def get_next_replica_url() -> str:
    """Thread-safe round-robin replica URL selector."""
    async with _replica_lock:
        return next(_replica_cycle)


async def get_write_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a write (primary) database session."""
    async with _primary_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


async def get_read_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a read (replica, round-robin) database session."""
    replica_url = await get_next_replica_url()
    engine = _replica_engines[replica_url]
    session_factory = async_sessionmaker(
        bind=engine,
        class_=AsyncSession,
        expire_on_commit=False,
    )
    async with session_factory() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise


async def dispose_engines() -> None:
    """Dispose all database engines. Called during shutdown."""
    await _primary_engine.dispose()
    for engine in _replica_engines.values():
        await engine.dispose()
    logger.info("All database engines disposed.")
