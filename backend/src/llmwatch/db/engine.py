"""
Module: engine.py
Purpose: Async SQLAlchemy engine and session setup for SQLite (default) or Postgres.
WHY: SQLite needs per-connection pragmas to behave well as an application database:
WAL lets readers proceed while a writer commits (dashboards stay responsive during
eval runs), foreign_keys=ON makes ON DELETE CASCADE actually work, and busy_timeout
makes concurrent writers wait instead of failing immediately with "database is locked".
"""

from collections.abc import AsyncIterator
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool

from llmwatch.config import settings


def is_memory_sqlite(url: str) -> bool:
    database = make_url(url).database
    return database in (None, "", ":memory:") or "mode=memory" in url


def create_engine(url: str, *, echo: bool = False) -> AsyncEngine:
    """Creates an async engine, applying SQLite pragmas when relevant."""
    parsed = make_url(url)
    is_sqlite = parsed.get_backend_name() == "sqlite"
    kwargs: dict = {"echo": echo}

    if is_sqlite:
        if is_memory_sqlite(url):
            # WHY: A memory database lives inside one connection; share it.
            kwargs["poolclass"] = StaticPool
            kwargs["connect_args"] = {"check_same_thread": False}
        elif parsed.database:
            Path(parsed.database).expanduser().parent.mkdir(parents=True, exist_ok=True)

    engine = create_async_engine(url, **kwargs)

    if is_sqlite:
        memory = is_memory_sqlite(url)

        @event.listens_for(engine.sync_engine, "connect")
        def _sqlite_pragmas(dbapi_connection, _record):  # pragma: no cover - trivial
            cursor = dbapi_connection.cursor()
            cursor.execute("PRAGMA foreign_keys=ON")
            cursor.execute("PRAGMA busy_timeout=5000")
            if not memory:
                cursor.execute("PRAGMA journal_mode=WAL")
                cursor.execute("PRAGMA synchronous=NORMAL")
            cursor.close()

    return engine


# WHY: Created lazily so importing this module has no side effects (no engine, no
# data directory) until the database is actually used.
_engine: AsyncEngine | None = None
_sessionmaker: async_sessionmaker[AsyncSession] | None = None


def get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = create_engine(settings.database_url, echo=settings.db_echo)
    return _engine


def get_sessionmaker() -> async_sessionmaker[AsyncSession]:
    global _sessionmaker
    if _sessionmaker is None:
        _sessionmaker = async_sessionmaker(get_engine(), expire_on_commit=False)
    return _sessionmaker


async def dispose_engine() -> None:
    global _engine, _sessionmaker
    if _engine is not None:
        await _engine.dispose()
    _engine = None
    _sessionmaker = None


async def get_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding a session; rolls back if the request fails."""
    async with get_sessionmaker()() as session:
        try:
            yield session
        except Exception:
            await session.rollback()
            raise
