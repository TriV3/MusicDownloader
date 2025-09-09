from __future__ import annotations

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase
import os


DATABASE_URL = os.environ.get("DATABASE_URL", "sqlite+aiosqlite:///./music.db")


class Base(DeclarativeBase):
    pass


engine = create_async_engine(
    DATABASE_URL, echo=False, future=True
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
