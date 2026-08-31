import sqlite3
from pathlib import Path

import pytest
import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations

from ion_api.migrations import upgrade_to_head


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
        assert revision == ("0007_calendar_write_foundation",)

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
    assert revision == ("0007_calendar_write_foundation",)
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
        ).fetchone() == ("0007_calendar_write_foundation",)


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
        ).fetchone() == ("0007_calendar_write_foundation",)

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
        ).fetchone() == ("0007_calendar_write_foundation",)


def test_calendar_presentation_metadata_migration_preserves_and_reverses(tmp_path):
    database_path = tmp_path / "calendar-presentation-migration.sqlite3"
    config = migration_config(database_path)
    command.upgrade(config, "0005_google_calendar_foundation")

    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO google_accounts "
            "(id, provider_account_id, display_name, granted_scopes, auth_state, "
            "keychain_locator, created_at, updated_at, revision) VALUES "
            "('account-a', 'synthetic@example.invalid', 'Synthetic', '[]', "
            "'connected', 'synthetic-locator', '2030-01-01T00:00:00Z', "
            "'2030-01-01T00:00:00Z', 1)"
        )
        connection.execute(
            "INSERT INTO google_calendars "
            "(id, account_id, provider_calendar_id, summary, access_role, "
            "is_primary, provider_selected, provider_hidden, enabled_in_ion, "
            "provider_deleted, sync_state, retry_count, created_at, updated_at, "
            "revision) VALUES ('calendar-a', 'account-a', 'calendar@example.invalid', "
            "'Synthetic calendar', 'owner', 1, 1, 0, 1, 0, 'idle', 0, "
            "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', 1)"
        )
        connection.execute(
            "INSERT INTO calendar_blocks "
            "(id, source_kind, title, temporal_kind, start_at, end_at, "
            "start_timezone, end_timezone, status, transparency, "
            "recurrence_kind, recurrence_rules, created_at, updated_at, revision) "
            "VALUES ('block-a', 'google', 'Synthetic event', 'timed', "
            "'2030-01-01T09:00:00Z', '2030-01-01T10:00:00Z', 'UTC', 'UTC', "
            "'confirmed', "
            "'opaque', 'single', '[]', '2030-01-01T00:00:00Z', "
            "'2030-01-01T00:00:00Z', 1)"
        )
        connection.execute(
            "INSERT INTO calendar_block_ion_metadata "
            "(calendar_block_id, flexibility, notes, created_at, updated_at, revision) "
            "VALUES ('block-a', 'locked', 'Preserved synthetic note', "
            "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', 1)"
        )

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT hidden_in_ion FROM google_calendars WHERE id = 'calendar-a'"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT notes, category, category_subtype "
            "FROM calendar_block_ion_metadata "
            "WHERE calendar_block_id = 'block-a'"
        ).fetchone() == ("Preserved synthetic note", None, None)
        connection.execute(
            "UPDATE google_calendars SET hidden_in_ion = 1 WHERE id = 'calendar-a'"
        )
        connection.execute(
            "UPDATE calendar_block_ion_metadata "
            "SET category = 'academic', category_subtype = 'homework_study' "
            "WHERE calendar_block_id = 'block-a'"
        )
        assert connection.execute(
            "SELECT category, category_subtype FROM calendar_block_ion_metadata "
            "WHERE calendar_block_id = 'block-a'"
        ).fetchone() == ("academic", "homework_study")
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE calendar_block_ion_metadata SET category = 'invalid' "
                "WHERE calendar_block_id = 'block-a'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE calendar_block_ion_metadata "
                "SET category_subtype = 'Invalid subtype' "
                "WHERE calendar_block_id = 'block-a'"
            )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE calendar_block_ion_metadata "
                "SET category = NULL, category_subtype = 'homework_study' "
                "WHERE calendar_block_id = 'block-a'"
            )
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0007_calendar_write_foundation",)

    command.downgrade(config, "0005_google_calendar_foundation")
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
        assert "hidden_in_ion" not in calendar_columns
        assert "category" not in metadata_columns
        assert "category_subtype" not in metadata_columns
        assert connection.execute(
            "SELECT notes FROM calendar_block_ion_metadata "
            "WHERE calendar_block_id = 'block-a'"
        ).fetchone() == ("Preserved synthetic note",)

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT hidden_in_ion FROM google_calendars WHERE id = 'calendar-a'"
        ).fetchone() == (0,)
        assert connection.execute(
            "SELECT category, category_subtype FROM calendar_block_ion_metadata "
            "WHERE calendar_block_id = 'block-a'"
        ).fetchone() == (None, None)


def test_runtime_repairs_only_the_interrupted_unreleased_0006_schema(tmp_path):
    database_path = tmp_path / "interrupted-0006.sqlite3"
    config = migration_config(database_path)
    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        connection.execute(
            "INSERT INTO calendar_blocks "
            "(id, source_kind, title, temporal_kind, start_at, end_at, "
            "start_timezone, end_timezone, status, transparency, "
            "recurrence_kind, recurrence_rules, created_at, updated_at, revision) "
            "VALUES ('block-repair', 'google', 'Synthetic repair event', 'timed', "
            "'2030-01-01T09:00:00Z', '2030-01-01T10:00:00Z', 'UTC', 'UTC', "
            "'confirmed', 'opaque', 'single', '[]', '2030-01-01T00:00:00Z', "
            "'2030-01-01T00:00:00Z', 1)"
        )
        connection.execute(
            "INSERT INTO calendar_block_ion_metadata "
            "(calendar_block_id, flexibility, notes, category, created_at, "
            "updated_at, revision) VALUES ('block-repair', 'locked', "
            "'Preserved synthetic repair note', 'academic', "
            "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', 3)"
        )

    engine = sa.create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        operations = Operations(MigrationContext.configure(connection))
        with operations.batch_alter_table("calendar_block_ion_metadata") as batch:
            batch.drop_constraint(
                "calendar_block_category_subtype_valid", type_="check"
            )
            batch.drop_column("category_subtype")
    engine.dispose()

    upgrade_to_head(database_path)
    with sqlite3.connect(database_path) as connection:
        columns = {
            row[1]
            for row in connection.execute(
                "PRAGMA table_info(calendar_block_ion_metadata)"
            )
        }
        preserved = connection.execute(
            "SELECT notes, category, category_subtype, revision "
            "FROM calendar_block_ion_metadata "
            "WHERE calendar_block_id = 'block-repair'"
        ).fetchone()
        assert "category_subtype" in columns
        assert preserved == (
            "Preserved synthetic repair note",
            "academic",
            None,
            3,
        )
        connection.execute(
            "UPDATE calendar_block_ion_metadata "
            "SET category_subtype = 'homework_study' "
            "WHERE calendar_block_id = 'block-repair'"
        )
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE calendar_block_ion_metadata "
                "SET category_subtype = 'Invalid subtype' "
                "WHERE calendar_block_id = 'block-repair'"
            )

    command.downgrade(config, "0005_google_calendar_foundation")
    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0007_calendar_write_foundation",)


def test_runtime_repairs_stale_unreleased_0006_category_constraint(tmp_path):
    database_path = tmp_path / "stale-category-0006.sqlite3"
    config = migration_config(database_path)
    command.upgrade(config, "head")
    engine = sa.create_engine(f"sqlite:///{database_path}")
    with engine.begin() as connection:
        connection.execute(
            sa.text(
                "INSERT INTO calendar_blocks "
                "(id, source_kind, title, temporal_kind, start_at, end_at, "
                "start_timezone, end_timezone, status, transparency, "
                "recurrence_kind, recurrence_rules, created_at, updated_at, revision) "
                "VALUES ('block-preserved', 'google', 'Synthetic preserved event', "
                "'timed', '2030-01-01T09:00:00Z', '2030-01-01T10:00:00Z', "
                "'UTC', 'UTC', 'confirmed', 'opaque', 'single', '[]', "
                "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', 1)"
            )
        )
        connection.execute(
            sa.text(
                "INSERT INTO calendar_block_ion_metadata "
                "(calendar_block_id, flexibility, notes, category, category_subtype, "
                "created_at, updated_at, revision) VALUES "
                "('block-preserved', 'locked', 'Synthetic preserved note', 'academic', "
                "'homework_study', '2030-01-01T00:00:00Z', "
                "'2030-01-01T00:00:00Z', 4)"
            )
        )
        operations = Operations(MigrationContext.configure(connection))
        with operations.batch_alter_table("calendar_block_ion_metadata") as batch:
            batch.drop_constraint("calendar_block_category_valid", type_="check")
            batch.create_check_constraint(
                "calendar_block_category_valid",
                "category IS NULL OR category IN "
                "('academic', 'work', 'meals', 'health', 'personal', 'ion_focus')",
            )
        for legacy_category in ["work", "meals", "health"]:
            connection.execute(
                sa.text(
                    "INSERT INTO calendar_blocks "
                    "(id, source_kind, title, temporal_kind, start_at, end_at, "
                    "start_timezone, end_timezone, status, transparency, "
                    "recurrence_kind, recurrence_rules, created_at, updated_at, "
                    "revision) "
                    "VALUES (:id, 'google', 'Synthetic legacy event', 'timed', "
                    "'2030-01-01T09:00:00Z', '2030-01-01T10:00:00Z', 'UTC', 'UTC', "
                    "'confirmed', 'opaque', 'single', '[]', '2030-01-01T00:00:00Z', "
                    "'2030-01-01T00:00:00Z', 1)"
                ),
                {"id": f"block-legacy-{legacy_category}"},
            )
            connection.execute(
                sa.text(
                    "INSERT INTO calendar_block_ion_metadata "
                    "(calendar_block_id, flexibility, notes, category, "
                    "category_subtype, "
                    "created_at, updated_at, revision) VALUES "
                    "(:id, 'locked', 'Synthetic legacy note', :category, NULL, "
                    "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', 2)"
                ),
                {
                    "id": f"block-legacy-{legacy_category}",
                    "category": legacy_category,
                },
            )
    engine.dispose()

    upgrade_to_head(database_path)
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT notes, category, category_subtype, revision "
            "FROM calendar_block_ion_metadata "
            "WHERE calendar_block_id = 'block-preserved'"
        ).fetchone() == (
            "Synthetic preserved note",
            "academic",
            "homework_study",
            4,
        )
        assert connection.execute(
            "SELECT category, category_subtype FROM calendar_block_ion_metadata "
            "WHERE calendar_block_id = 'block-legacy-work'"
        ).fetchone() == ("routine_physical", "work_shift")
        assert connection.execute(
            "SELECT category, category_subtype FROM calendar_block_ion_metadata "
            "WHERE calendar_block_id = 'block-legacy-meals'"
        ).fetchone() == ("routine_physical", "meal")
        assert connection.execute(
            "SELECT category, category_subtype FROM calendar_block_ion_metadata "
            "WHERE calendar_block_id = 'block-legacy-health'"
        ).fetchone() == ("routine_physical", "health")
        for category in [
            "academic",
            "career",
            "personal_project",
            "routine_physical",
            "personal",
            "fun",
            "ion_focus",
        ]:
            connection.execute(
                "INSERT INTO calendar_blocks "
                "(id, source_kind, title, temporal_kind, start_at, end_at, "
                "start_timezone, end_timezone, status, transparency, "
                "recurrence_kind, recurrence_rules, created_at, updated_at, revision) "
                "VALUES (?, 'google', 'Synthetic category repair', 'timed', "
                "'2030-01-01T09:00:00Z', '2030-01-01T10:00:00Z', 'UTC', 'UTC', "
                "'confirmed', 'opaque', 'single', '[]', '2030-01-01T00:00:00Z', "
                "'2030-01-01T00:00:00Z', 1)",
                (f"block-{category}",),
            )
            connection.execute(
                "INSERT INTO calendar_block_ion_metadata "
                "(calendar_block_id, flexibility, category, category_subtype, "
                "created_at, updated_at, revision) VALUES (?, 'locked', ?, ?, "
                "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', 1)",
                (
                    f"block-{category}",
                    category,
                    None if category == "ion_focus" else "synthetic_subtype",
                ),
            )
        assert connection.execute(
            "SELECT count(*) FROM calendar_block_ion_metadata"
        ).fetchone() == (11,)


def test_calendar_write_foundation_migration_upgrade_downgrade_and_preservation(
    tmp_path,
):
    database_path = tmp_path / "calendar-write-foundation.sqlite3"
    config = migration_config(database_path)
    command.upgrade(config, "0006_calendar_presentation_metadata")
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute(
            "INSERT INTO areas (id, created_at, updated_at, revision, name) VALUES "
            "('area-preserved', '2030-01-01T00:00:00Z', "
            "'2030-01-01T00:00:00Z', 1, 'Synthetic Area')"
        )
        connection.execute(
            "INSERT INTO goals (id, area_id, created_at, updated_at, revision, "
            "title, kind, state) VALUES ('goal-preserved', 'area-preserved', "
            "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', 1, "
            "'Synthetic Goal', 'outcome', 'active')"
        )
        connection.execute(
            "INSERT INTO projects (id, goal_id, created_at, updated_at, revision, "
            "title, state) VALUES ('project-preserved', 'goal-preserved', "
            "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', 1, "
            "'Synthetic Project', 'active')"
        )
        connection.execute(
            "INSERT INTO tasks (id, project_id, goal_id, created_at, updated_at, "
            "revision, title, state, source_kind, deadline_kind) VALUES "
            "('task-preserved', 'project-preserved', 'goal-preserved', "
            "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', 1, "
            "'Synthetic Task', 'open', 'human', 'none')"
        )
        connection.execute(
            "INSERT INTO google_accounts (id, provider_account_id, display_name, "
            "granted_scopes, keychain_locator, auth_state, created_at, updated_at, "
            "revision) VALUES ('account-preserved', 'synthetic@example.invalid', "
            "'Synthetic Account', '[]', 'synthetic-keychain-locator', 'connected', "
            "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', 1)"
        )
        connection.execute(
            "INSERT INTO google_calendars (id, account_id, provider_calendar_id, "
            "summary, access_role, is_primary, provider_selected, provider_hidden, "
            "enabled_in_ion, hidden_in_ion, provider_deleted, next_sync_token, "
            "sync_state, retry_count, created_at, updated_at, revision) VALUES "
            "('calendar-preserved', 'account-preserved', "
            "'calendar@example.invalid', 'Synthetic Calendar', 'owner', 1, 1, 0, "
            "1, 0, 0, 'synthetic-sync-token', 'idle', 0, "
            "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', 3)"
        )
        connection.execute(
            "INSERT INTO calendar_blocks (id, source_kind, title, temporal_kind, "
            "start_at, end_at, start_timezone, end_timezone, status, transparency, "
            "recurrence_kind, recurrence_rules, created_at, updated_at, revision) "
            "VALUES ('block-preserved', 'google', 'Synthetic Event', 'timed', "
            "'2030-01-01T09:00:00Z', '2030-01-01T10:00:00Z', 'UTC', 'UTC', "
            "'confirmed', 'opaque', 'single', '[]', '2030-01-01T00:00:00Z', "
            "'2030-01-01T00:00:00Z', 7)"
        )
        connection.execute(
            "INSERT INTO calendar_block_ion_metadata (calendar_block_id, "
            "flexibility, notes, category, category_subtype, created_at, updated_at, "
            "revision) VALUES ('block-preserved', 'flexible', "
            "'Synthetic preserved note', 'academic', 'homework_study', "
            "'2030-01-01T00:00:00Z', '2030-01-01T00:00:00Z', 4)"
        )
        connection.execute(
            "INSERT INTO google_event_links (calendar_block_id, account_id, "
            "calendar_id, provider_event_id, ical_uid, provider_etag, "
            "provider_updated_at, original_start_kind, last_seen_sync_generation) "
            "VALUES ('block-preserved', 'account-preserved', 'calendar-preserved', "
            "'synthetic-event', 'synthetic-event@example.invalid', "
            "'synthetic-etag', '2030-01-01T00:00:00Z', 'none', "
            "'11111111-1111-4111-8111-111111111111')"
        )

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        connection.execute("PRAGMA foreign_keys = ON")
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        assert {
            "calendar_provider_write_intents",
            "calendar_provider_write_audit",
        } <= tables
        assert connection.execute(
            "SELECT calendar_write_scope_state FROM google_accounts "
            "WHERE id = 'account-preserved'"
        ).fetchone() == ("read_only",)
        assert connection.execute(
            "SELECT link_state, provider_event_type, provider_locked, has_attendees, "
            "last_seen_sync_generation FROM google_event_links "
            "WHERE calendar_block_id = 'block-preserved'"
        ).fetchone() == (
            "confirmed",
            "default",
            0,
            0,
            "11111111-1111-4111-8111-111111111111",
        )
        assert connection.execute(
            "SELECT title, revision FROM tasks WHERE id = 'task-preserved'"
        ).fetchone() == ("Synthetic Task", 1)
        assert connection.execute(
            "SELECT notes, category, category_subtype, revision "
            "FROM calendar_block_ion_metadata WHERE calendar_block_id = "
            "'block-preserved'"
        ).fetchone() == (
            "Synthetic preserved note",
            "academic",
            "homework_study",
            4,
        )
        assert connection.execute(
            "SELECT next_sync_token, revision FROM google_calendars "
            "WHERE id = 'calendar-preserved'"
        ).fetchone() == ("synthetic-sync-token", 3)
        with pytest.raises(sqlite3.IntegrityError):
            connection.execute(
                "UPDATE google_accounts SET calendar_write_scope_state = 'broad' "
                "WHERE id = 'account-preserved'"
            )

    command.downgrade(config, "0006_calendar_presentation_metadata")
    with sqlite3.connect(database_path) as connection:
        tables = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            )
        }
        account_columns = {
            row[1] for row in connection.execute("PRAGMA table_info(google_accounts)")
        }
        link_columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(google_event_links)")
        }
        assert "calendar_provider_write_intents" not in tables
        assert "calendar_provider_write_audit" not in tables
        assert "calendar_write_scope_state" not in account_columns
        assert "provider_event_type" not in link_columns
        assert connection.execute(
            "SELECT title FROM tasks WHERE id = 'task-preserved'"
        ).fetchone() == ("Synthetic Task",)
        assert connection.execute(
            "SELECT provider_event_id, last_seen_sync_generation "
            "FROM google_event_links WHERE calendar_block_id = 'block-preserved'"
        ).fetchone() == (
            "synthetic-event",
            "11111111-1111-4111-8111-111111111111",
        )

    command.upgrade(config, "head")
    with sqlite3.connect(database_path) as connection:
        assert connection.execute(
            "SELECT version_num FROM alembic_version"
        ).fetchone() == ("0007_calendar_write_foundation",)
        assert connection.execute(
            "SELECT calendar_write_scope_state FROM google_accounts "
            "WHERE id = 'account-preserved'"
        ).fetchone() == ("read_only",)
