from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool
from sqlalchemy.orm import DeclarativeBase
import os


try:
    # Prefer importing centralized settings (which loads .env)
    from ..core.config import settings  # type: ignore
except Exception:  # pragma: no cover
    from core.config import settings  # type: ignore

DATABASE_URL = settings.database_url


class Base(DeclarativeBase):
    pass


engine_kwargs = {"echo": False, "future": True}
if DATABASE_URL.startswith("sqlite+aiosqlite"):
    # Allow cross-thread usage and enable SQLite URI mode when using file: URLs.
    connect_args = {"check_same_thread": False}
    # If using the SQLite URI form (e.g., sqlite+aiosqlite:///file:memdb1?...&uri=true),
    # SQLAlchemy requires connect_args["uri"] = True so the driver interprets it as a URI.
    if "file:" in DATABASE_URL or "uri=true" in DATABASE_URL:
        connect_args["uri"] = True
    engine_kwargs["connect_args"] = connect_args
    # Ensure in-memory DB is shared across sessions (tests/workers)
    if DATABASE_URL.endswith(":memory:") or ":memory:" in DATABASE_URL:
        engine_kwargs["poolclass"] = StaticPool  # type: ignore[assignment]

engine = create_async_engine(
    DATABASE_URL, **engine_kwargs
)

async_session = async_sessionmaker(
    bind=engine, expire_on_commit=False, class_=AsyncSession
)


async def get_session() -> AsyncGenerator[AsyncSession, None]:
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
