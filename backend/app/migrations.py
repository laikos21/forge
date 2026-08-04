"""Programmatic access to Alembic.

Migrations run automatically at application startup so that ``run.ps1`` is a
single command and a restored backup is always brought up to the current schema.
The same functions back the ``forge-db`` CLI in ``scripts/manage.py``.
"""

from __future__ import annotations

from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.runtime.migration import MigrationContext
from alembic.script import ScriptDirectory

from .config import get_settings
from .db import get_engine

BACKEND_DIR = Path(__file__).resolve().parent.parent


def alembic_config() -> Config:
    config = Config(str(BACKEND_DIR / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    config.set_main_option("sqlalchemy.url", get_settings().database_url)
    return config


def current_revision() -> str | None:
    with get_engine().connect() as connection:
        return MigrationContext.configure(connection).get_current_revision()


def head_revision() -> str | None:
    return ScriptDirectory.from_config(alembic_config()).get_current_head()


def upgrade_to_head() -> str | None:
    get_settings().ensure_dirs()
    command.upgrade(alembic_config(), "head")
    return current_revision()


def is_up_to_date() -> bool:
    return current_revision() == head_revision()


def stamp_head() -> None:
    command.stamp(alembic_config(), "head")
