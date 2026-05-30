"""Async SQLAlchemy engine, session factory, declarative base, and FastAPI dep."""
from __future__ import annotations

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import NullPool

from app.core.config import get_settings

settings = get_settings()


class Base(DeclarativeBase):
    pass


# Under pytest each test runs in its own event loop; a pooled asyncpg
# connection opened in one loop fails when torn down in another. NullPool
# gives each session a fresh connection within the same loop. Production
# keeps a real pool.
if settings.testing:
    engine = create_async_engine(settings.database_url, poolclass=NullPool)
else:
    engine = create_async_engine(
        settings.database_url, pool_pre_ping=True, pool_size=10, max_overflow=20
    )

SessionLocal = async_sessionmaker(
    bind=engine, class_=AsyncSession, expire_on_commit=False, autoflush=False
)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    async with SessionLocal() as session:
        yield session
