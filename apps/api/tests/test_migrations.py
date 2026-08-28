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
        assert revision == ("0003_milestone_ordering",)

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
