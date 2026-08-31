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

        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }

    assert version == ("0006_calendar_presentation_metadata",)
    assert {
        "areas",
        "goals",
        "milestones",
        "projects",
        "project_milestones",
        "tasks",
        "audit_events",
        "task_day_plans",
        "google_accounts",
        "google_calendars",
        "calendar_blocks",
        "calendar_block_ion_metadata",
        "google_event_links",
    } <= tables

    with sqlite3.connect(database_path) as connection:
        milestone_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(milestones)")
        }
        project_milestone_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(project_milestones)")
        }

    assert "position" in milestone_columns
    assert "position" in project_milestone_columns

    with sqlite3.connect(database_path) as connection:
        calendar_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(google_calendars)")
        }
        metadata_columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(calendar_block_ion_metadata)"
            )
        }

    assert "hidden_in_ion" in calendar_columns
    assert "category" in metadata_columns
    assert "category_subtype" in metadata_columns
