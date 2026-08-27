import sqlite3

from alembic import command
from alembic.config import Config


def test_alembic_upgrades_a_fresh_user_local_database(tmp_path, monkeypatch):
    monkeypatch.setenv("ION_DATA_DIR", str(tmp_path))
    config = Config("alembic.ini")

    command.upgrade(config, "head")

    database_path = tmp_path / "ion-development.sqlite3"
    with sqlite3.connect(database_path) as connection:
        version = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()

    assert version == ("0001_baseline",)
