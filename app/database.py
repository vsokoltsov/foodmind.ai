"""Async SQLAlchemy engine and session management."""

from collections.abc import AsyncIterator

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

from app.models.base import Base
from app.settings import get_settings


def create_engine() -> AsyncEngine:
    """Create the application async database engine from settings."""
    return create_async_engine(get_settings().DATABASE_URL, pool_pre_ping=True)


engine = create_engine()
SessionFactory = async_sessionmaker(engine, expire_on_commit=False)


async def get_session() -> AsyncIterator[AsyncSession]:
    """Yield an application-managed async database session."""
    async with SessionFactory() as session:
        yield session


async def create_tables() -> None:
    """Create application tables for local development.

    Production schema changes should be applied through Alembic migrations.
    """
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
