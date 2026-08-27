from __future__ import annotations

from pathlib import Path

from sqlalchemy import Engine, create_engine


def database_url(path: Path) -> str:
    return f"sqlite:///{path}"


def create_database_engine(path: Path) -> Engine:
    """Create a local SQLite engine; schema ownership remains future work."""

    path.parent.mkdir(parents=True, exist_ok=True)
    return create_engine(database_url(path))
