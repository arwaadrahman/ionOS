"""Programmatic Alembic entry point for source and frozen sidecar runtimes."""

from __future__ import annotations

import sys
from pathlib import Path

from alembic import command
from alembic.config import Config

from ion_api.db import database_url


def migration_assets_root() -> Path:
    """Return the directory containing bundled Alembic configuration/assets."""

    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def upgrade_to_head(database_path: Path) -> None:
    root = migration_assets_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url(database_path))
    config.attributes["ion_explicit_database_url"] = True
    command.upgrade(config, "head")
