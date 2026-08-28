"""Add canonical human Today planning intent.

Revision ID: 0004_today_planning
Revises: 0003_milestone_ordering
Create Date: 2026-08-28
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0004_today_planning"
down_revision: str | None = "0003_milestone_ordering"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "task_day_plans",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_id", sa.String(length=36), nullable=False),
        sa.Column("planning_date", sa.String(), nullable=False),
        sa.Column("role", sa.String(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "length(planning_date) = 10 AND "
            "planning_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'",
            name="task_day_plan_date_shape_valid",
        ),
        sa.CheckConstraint(
            "role IN ('priority', 'planned', 'backup')",
            name="task_day_plan_role_valid",
        ),
        sa.CheckConstraint("position >= 0", name="task_day_plan_position_nonnegative"),
        sa.CheckConstraint("revision >= 1", name="task_day_plan_revision_positive"),
        sa.ForeignKeyConstraint(["task_id"], ["tasks.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "task_id", "planning_date", name="uq_task_day_plans_task_date"
        ),
        sa.UniqueConstraint(
            "planning_date",
            "role",
            "position",
            name="uq_task_day_plans_date_role_position",
        ),
    )


def downgrade() -> None:
    op.drop_table("task_day_plans")
