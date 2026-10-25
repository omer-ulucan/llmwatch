"""Alembic environment: async engine, SQLite batch mode, URL from settings."""

import asyncio

from alembic import context
from sqlalchemy.engine import Connection

from llmwatch.config import settings
from llmwatch.db.engine import create_engine
from llmwatch.db.models import Base

config = context.config
target_metadata = Base.metadata


def _database_url() -> str:
    return (
        config.attributes.get("database_url")
        or config.get_main_option("sqlalchemy.url")
        or settings.database_url
    )


def run_migrations_offline() -> None:
    url = _database_url()
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        render_as_batch=url.startswith("sqlite"),
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def _run(connection: Connection) -> None:
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
        # WHY: SQLite can't ALTER most things; batch mode rebuilds tables instead.
        render_as_batch=connection.dialect.name == "sqlite",
        compare_type=True,
    )
    with context.begin_transaction():
        context.run_migrations()


async def _run_async() -> None:
    engine = create_engine(_database_url())
    async with engine.connect() as connection:
        if connection.dialect.name == "sqlite":
            # WHY: Batch mode drops and recreates tables; with foreign keys on, that
            # would cascade-delete child rows. Must be set outside a transaction.
            await connection.exec_driver_sql("PRAGMA foreign_keys=OFF")
        await connection.run_sync(_run)
        await connection.commit()
    await engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    asyncio.run(_run_async())
