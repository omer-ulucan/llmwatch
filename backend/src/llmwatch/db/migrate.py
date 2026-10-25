"""
Module: migrate.py
Purpose: Runs Alembic migrations programmatically.
WHY: Migrations ship inside the package so an installed server (Docker image, pip
install) can upgrade its own database at startup, with no alembic.ini lying around.
"""

from pathlib import Path

from alembic import command
from alembic.config import Config

MIGRATIONS_DIR = Path(__file__).with_name("migrations")


def alembic_config(database_url: str) -> Config:
    cfg = Config()
    cfg.set_main_option("script_location", str(MIGRATIONS_DIR))
    cfg.attributes["database_url"] = database_url
    return cfg


def upgrade(database_url: str, revision: str = "head") -> None:
    """Upgrades the database. Blocking: call via asyncio.to_thread from async code."""
    command.upgrade(alembic_config(database_url), revision)


def downgrade(database_url: str, revision: str) -> None:
    command.downgrade(alembic_config(database_url), revision)
