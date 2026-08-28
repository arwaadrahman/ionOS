"""Add stable owner-scoped milestone ordering.

Revision ID: 0003_milestone_ordering
Revises: 0002_organizer_foundation
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_milestone_ordering"
down_revision: str | None = "0002_organizer_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def _add_ordering(
    table: str,
    owner_column: str,
    check_name: str,
    unique_name: str,
) -> None:
    op.add_column(table, sa.Column("position", sa.Integer(), nullable=True))
    op.execute(
        sa.text(
            f"""
            UPDATE {table} AS current
            SET position = (
                SELECT COUNT(*)
                FROM {table} AS prior
                WHERE prior.{owner_column} = current.{owner_column}
                  AND (
                    prior.created_at < current.created_at
                    OR (
                      prior.created_at = current.created_at
                      AND prior.id < current.id
                    )
                  )
            )
            """
        )
    )
    with op.batch_alter_table(table, recreate="always") as batch:
        batch.alter_column("position", existing_type=sa.Integer(), nullable=False)
        batch.create_check_constraint(check_name, "position >= 0")
        batch.create_unique_constraint(unique_name, [owner_column, "position"])


def upgrade() -> None:
    _add_ordering(
        "milestones",
        "goal_id",
        "milestone_position_nonnegative",
        "uq_milestones_goal_position",
    )
    _add_ordering(
        "project_milestones",
        "project_id",
        "project_milestone_position_nonnegative",
        "uq_project_milestones_project_position",
    )


def _drop_ordering(table: str, check_name: str, unique_name: str) -> None:
    with op.batch_alter_table(table, recreate="always") as batch:
        batch.drop_constraint(unique_name, type_="unique")
        batch.drop_constraint(check_name, type_="check")
        batch.drop_column("position")


def downgrade() -> None:
    _drop_ordering(
        "project_milestones",
        "project_milestone_position_nonnegative",
        "uq_project_milestones_project_position",
    )
    _drop_ordering(
        "milestones",
        "milestone_position_nonnegative",
        "uq_milestones_goal_position",
    )
