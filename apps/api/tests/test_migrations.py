import sqlite3
from pathlib import Path

import pytest
from alembic import command
from alembic.config import Config


def migration_config(database_path: Path) -> Config:
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", f"sqlite:///{database_path}")
    config.attributes["ion_explicit_database_url"] = True
    return config


def organizer_values(entity_id: str, created_at: str, trashed_at: str | None = None):
    return (entity_id, created_at, created_at, 1, trashed_at)


def test_milestone_ordering_migration_is_reversible_and_deterministic(tmp_path):
    database_path = tmp_path / "migration.sqlite3"
    config = migration_config(database_path)
    command.upgrade(config, "0002_organizer_foundation")

    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO goals "
            "(id, created_at, updated_at, revision, trashed_at, title, kind, state) "
            "VALUES (?, ?, ?, ?, ?, 'Goal A', 'outcome', 'active')",
            organizer_values("goal-a", "2026-01-01T00:00:00Z"),
        )
        connection.execute(
            "INSERT INTO goals "
            "(id, created_at, updated_at, revision, trashed_at, title, kind, state) "
            "VALUES (?, ?, ?, ?, ?, 'Goal B', 'outcome', 'active')",
            organizer_values("goal-b", "2026-01-01T00:00:00Z"),
        )
        connection.execute(
            "INSERT INTO projects "
            "(id, created_at, updated_at, revision, trashed_at, title, state) "
            "VALUES (?, ?, ?, ?, ?, 'Project A', 'active')",
            organizer_values("project-a", "2026-01-01T00:00:00Z"),
        )
        connection.execute(
            "INSERT INTO projects "
            "(id, created_at, updated_at, revision, trashed_at, title, state) "
            "VALUES (?, ?, ?, ?, ?, 'Project B', 'active')",
            organizer_values("project-b", "2026-01-01T00:00:00Z"),
        )

        for milestone_id, goal_id, created_at, trashed_at in (
            ("m-c", "goal-a", "2026-01-03T00:00:00Z", None),
            ("m-b", "goal-a", "2026-01-02T00:00:00Z", "2026-02-01T00:00:00Z"),
            ("m-a", "goal-a", "2026-01-02T00:00:00Z", None),
            ("m-d", "goal-b", "2026-01-01T00:00:00Z", None),
        ):
            connection.execute(
                "INSERT INTO milestones "
                "(id, created_at, updated_at, revision, trashed_at, goal_id, "
                "title, state) VALUES (?, ?, ?, 1, ?, ?, ?, 'planned')",
                (
                    milestone_id,
                    created_at,
                    created_at,
                    trashed_at,
                    goal_id,
                    milestone_id,
                ),
            )
        for milestone_id, created_at in (
            ("pm-b", "2026-01-02T00:00:00Z"),
            ("pm-a", "2026-01-01T00:00:00Z"),
        ):
            connection.execute(
                "INSERT INTO project_milestones "
                "(id, created_at, updated_at, revision, trashed_at, project_id, "
                "title, state) VALUES (?, ?, ?, 1, NULL, 'project-a', ?, 'planned')",
                (milestone_id, created_at, created_at, milestone_id),
            )
        connection.execute(
            "INSERT INTO project_milestones "
            "(id, created_at, updated_at, revision, trashed_at, project_id, "
            "title, state) VALUES ('pm-c', '2026-01-01T00:00:00Z', "
            "'2026-01-01T00:00:00Z', 1, NULL, 'project-b', 'pm-c', 'planned')"
        )

    command.upgrade(config, "head")

    with sqlite3.connect(database_path) as connection:
        goal_positions = connection.execute(
            "SELECT id, position FROM milestones WHERE goal_id = 'goal-a' "
            "ORDER BY position"
        ).fetchall()
        project_positions = connection.execute(
            "SELECT id, position FROM project_milestones "
            "WHERE project_id = 'project-a' ORDER BY position"
        ).fetchall()
        second_project_positions = connection.execute(
            "SELECT id, position FROM project_milestones "
            "WHERE project_id = 'project-b' ORDER BY position"
        ).fetchall()
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()

        assert goal_positions == [("m-a", 0), ("m-b", 1), ("m-c", 2)]
        assert project_positions == [("pm-a", 0), ("pm-b", 1)]
        assert second_project_positions == [("pm-c", 0)]
        assert revision == ("0005_google_calendar_foundation",)

        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "INSERT INTO milestones "
                "(id, created_at, updated_at, revision, goal_id, title, state, "
                "position) "
                "VALUES ('duplicate', 'now', 'now', 1, 'goal-a', 'Duplicate', "
                "'planned', 0)"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute("UPDATE milestones SET position = -1 WHERE id = 'm-a'")

    command.downgrade(config, "0002_organizer_foundation")
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1] for row in connection.execute("PRAGMA table_info(milestones)")
        }
        milestone_count = connection.execute(
            "SELECT COUNT(*) FROM milestones"
        ).fetchone()

    assert "position" not in columns
    assert milestone_count == (4,)

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        positions_after_reupgrade = connection.execute(
            "SELECT id, position FROM milestones WHERE goal_id = 'goal-a' "
            "ORDER BY position"
        ).fetchall()

    assert positions_after_reupgrade == [("m-a", 0), ("m-b", 1), ("m-c", 2)]


def test_today_planning_migration_preserves_0003_data_and_enforces_contract(tmp_path):
    database_path = tmp_path / "today-migration.sqlite3"
    config = migration_config(database_path)
    command.upgrade(config, "0003_milestone_ordering")
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO tasks "
            "(id, created_at, updated_at, revision, title, state, source_kind, "
            "deadline_kind) VALUES "
            "('task-a', '2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', "
            "1, 'Synthetic Task', 'open', 'human', 'none')"
        )
        connection.execute(
            "INSERT INTO tasks "
            "(id, created_at, updated_at, revision, title, state, source_kind, "
            "deadline_kind) VALUES "
            "('task-b', '2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', "
            "1, 'Second Synthetic Task', 'open', 'human', 'none')"
        )

    command.upgrade(config, "head")
    base = (
        "INSERT INTO task_day_plans "
        "(id, task_id, planning_date, role, position, created_at, updated_at, "
        "revision) "
        "VALUES (?, ?, ?, ?, ?, '2030-01-01T00:00:00Z', "
        "'2030-01-01T00:00:00Z', ?)"
    )
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        for values in (
            ("plan-a", "task-a", "2030-01-01", "priority", 0, 1),
            ("plan-b", "task-a", "2030-01-02", "planned", 0, 1),
            ("plan-c", "task-a", "2030-01-03", "backup", 0, 1),
        ):
            connection.execute(base, values)
        for values in (
            ("bad-role", "task-a", "2030-01-04", "later", 0, 1),
            ("bad-date", "task-a", "20300104", "planned", 0, 1),
            ("bad-position", "task-a", "2030-01-04", "planned", -1, 1),
            ("bad-revision", "task-a", "2030-01-04", "planned", 0, 0),
            ("duplicate-task-date", "task-a", "2030-01-01", "backup", 1, 1),
            ("duplicate-position", "task-b", "2030-01-01", "priority", 0, 1),
            ("missing-task", "missing", "2030-01-05", "planned", 0, 1),
        ):
            with pytest.raises(sqlite3.IntegrityError):
                connection.execute(base, values)
        revision = connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone()
        task_count = connection.execute("SELECT COUNT(*) FROM tasks").fetchone()
    assert revision == ("0005_google_calendar_foundation",)
    assert task_count == (2,)

    command.downgrade(config, "0003_milestone_ordering")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute("SELECT COUNT(*) FROM tasks").fetchone() == (2,)
        assert connection.execute(
            "SELECT COUNT(*) FROM sqlite_master "
            "WHERE type = 'table' AND name = 'task_day_plans'"
        ).fetchone() == (0,)
    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0005_google_calendar_foundation",)


def test_google_calendar_migration_fresh_upgrade_preservation_and_downgrade(tmp_path):
    database_path = tmp_path / "calendar-migration.sqlite3"
    config = migration_config(database_path)
    command.upgrade(config, "0004_today_planning")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO tasks "
            "(id, created_at, updated_at, revision, title, state, source_kind, "
            "deadline_kind) VALUES "
            "('preserved-task', '2030-01-01T00:00:00Z', "
            "'2030-01-01T00:00:00Z', 1, 'Preserved Synthetic Task', "
            "'open', 'human', 'none')"
        )

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "google_accounts",
            "google_calendars",
            "calendar_blocks",
            "calendar_block_ion_metadata",
            "google_event_links",
        } <= tables
        assert connection.execute(
            "SELECT title FROM tasks WHERE id = 'preserved-task'"
        ).fetchone() == ("Preserved Synthetic Task",)
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0005_google_calendar_foundation",)

    command.downgrade(config, "0004_today_planning")
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert "google_accounts" not in tables
        assert connection.execute(
            "SELECT title FROM tasks WHERE id = 'preserved-task'"
        ).fetchone() == ("Preserved Synthetic Task",)

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0005_google_calendar_foundation",)
