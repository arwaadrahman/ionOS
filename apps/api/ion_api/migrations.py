"""Programmatic Alembic entry point for source and frozen sidecar runtimes."""

from __future__ import annotations

import sys
from pathlib import Path

import sqlalchemy as sa
from alembic import command
from alembic.config import Config
from alembic.migration import MigrationContext
from alembic.operations import Operations

from ion_api.db import database_url

UNRELEASED_CALENDAR_PRESENTATION_REVISION = "0006_calendar_presentation_metadata"
CALENDAR_WRITE_FOUNDATION_REVISION = "0007_calendar_write_foundation"
CATEGORY_VALUES = (
    "academic",
    "career",
    "personal_project",
    "routine_physical",
    "personal",
    "fun",
    "ion_focus",
)
CATEGORY_CONSTRAINT = (
    "category IS NULL OR category IN "
    "('academic', 'career', 'personal_project', 'routine_physical', "
    "'personal', 'fun', 'ion_focus')"
)
CATEGORY_SUBTYPE_CONSTRAINT = (
    "category_subtype IS NULL OR (category IS NOT NULL "
    "AND length(category_subtype) BETWEEN 1 AND 64 "
    "AND category_subtype NOT GLOB '*[^a-z0-9_]*' "
    "AND category_subtype GLOB '[a-z]*')"
)


def migration_assets_root() -> Path:
    """Return the directory containing bundled Alembic configuration/assets."""

    if hasattr(sys, "_MEIPASS"):
        return Path(sys._MEIPASS)
    return Path(__file__).resolve().parents[1]


def _repair_interrupted_unreleased_0006(database_path: Path) -> None:
    """Bring every pre-acceptance 0006 shape to its current in-place schema."""

    if not database_path.is_file():
        return
    engine = sa.create_engine(database_url(database_path))
    try:
        with engine.connect() as connection:
            inspector = sa.inspect(connection)
            if not inspector.has_table("alembic_version") or not inspector.has_table(
                "calendar_block_ion_metadata"
            ):
                return
            revision = connection.scalar(
                sa.text("SELECT version_num FROM alembic_version")
            )
            columns = {
                column["name"]
                for column in inspector.get_columns("calendar_block_ion_metadata")
            }
            constraints = {
                constraint["name"]: constraint.get("sqltext") or ""
                for constraint in inspector.get_check_constraints(
                    "calendar_block_ion_metadata"
                )
                if constraint.get("name")
            }
        if (
            revision
            not in (
                UNRELEASED_CALENDAR_PRESENTATION_REVISION,
                CALENDAR_WRITE_FOUNDATION_REVISION,
            )
            or "category" not in columns
        ):
            return
        category_constraint = constraints.get("calendar_block_category_valid", "")
        repair_category_constraint = not all(
            f"'{value}'" in category_constraint for value in CATEGORY_VALUES
        )
        add_subtype_column = "category_subtype" not in columns
        repair_subtype_constraint = (
            add_subtype_column
            or "calendar_block_category_subtype_valid" not in constraints
        )
        if not repair_category_constraint and not repair_subtype_constraint:
            return
        with engine.begin() as connection:
            operations = Operations(MigrationContext.configure(connection))
            if repair_category_constraint:
                with operations.batch_alter_table(
                    "calendar_block_ion_metadata"
                ) as batch:
                    if category_constraint:
                        batch.drop_constraint(
                            "calendar_block_category_valid", type_="check"
                        )
                    if add_subtype_column:
                        batch.add_column(
                            sa.Column("category_subtype", sa.String(), nullable=True)
                        )
                    if repair_subtype_constraint:
                        batch.create_check_constraint(
                            "calendar_block_category_subtype_valid",
                            CATEGORY_SUBTYPE_CONSTRAINT,
                        )
                connection.execute(
                    sa.text(
                        "UPDATE calendar_block_ion_metadata SET "
                        "category_subtype = CASE category "
                        "WHEN 'work' THEN coalesce(category_subtype, 'work_shift') "
                        "WHEN 'meals' THEN coalesce(category_subtype, 'meal') "
                        "WHEN 'health' THEN coalesce(category_subtype, 'health') "
                        "ELSE category_subtype END, "
                        "category = CASE category "
                        "WHEN 'work' THEN 'routine_physical' "
                        "WHEN 'meals' THEN 'routine_physical' "
                        "WHEN 'health' THEN 'routine_physical' "
                        "ELSE category END"
                    )
                )
                with operations.batch_alter_table(
                    "calendar_block_ion_metadata"
                ) as batch:
                    batch.create_check_constraint(
                        "calendar_block_category_valid", CATEGORY_CONSTRAINT
                    )
            elif repair_subtype_constraint:
                with operations.batch_alter_table(
                    "calendar_block_ion_metadata"
                ) as batch:
                    if add_subtype_column:
                        batch.add_column(
                            sa.Column("category_subtype", sa.String(), nullable=True)
                        )
                    batch.create_check_constraint(
                        "calendar_block_category_subtype_valid",
                        CATEGORY_SUBTYPE_CONSTRAINT,
                    )
    finally:
        engine.dispose()


def upgrade_to_head(database_path: Path) -> None:
    root = migration_assets_root()
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "migrations"))
    config.set_main_option("sqlalchemy.url", database_url(database_path))
    config.attributes["ion_explicit_database_url"] = True
    _repair_interrupted_unreleased_0006(database_path)
    command.upgrade(config, "head")
    _repair_interrupted_unreleased_0006(database_path)
