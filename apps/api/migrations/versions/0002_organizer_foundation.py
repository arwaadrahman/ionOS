"""Phase 1A canonical organizer foundation.

Revision ID: 0002_organizer_foundation
Revises: 0001_baseline
Create Date: 2026-08-27
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0002_organizer_foundation"
down_revision: str | None = "0001_baseline"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
DEADLINE_UNION_CHECK = (
    "(deadline_kind = 'none' AND deadline_date IS NULL AND deadline_at IS NULL "
    "AND deadline_timezone IS NULL) OR "
    "(deadline_kind = 'date' AND deadline_date IS NOT NULL AND deadline_at IS NULL "
    "AND deadline_timezone IS NULL) OR "
    "(deadline_kind = 'instant' AND deadline_date IS NULL AND deadline_at IS NOT NULL "
    "AND deadline_timezone IS NOT NULL)"
)
COMPLETION_CHECK = (
    "(state = 'completed' AND completed_at IS NOT NULL) OR "
    "(state <> 'completed' AND completed_at IS NULL)"
)


def _organizer_columns() -> list[sa.Column]:
    return [
        sa.Column("id", sa.String(length=36), primary_key=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("trashed_at", sa.String(), nullable=True),
        sa.CheckConstraint("revision >= 1", name="revision_positive"),
    ]


def upgrade() -> None:
    op.create_table(
        "areas",
        *_organizer_columns(),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("archived_at", sa.String(), nullable=True),
        sa.CheckConstraint("length(trim(name)) > 0", name="area_name_present"),
    )
    op.create_table(
        "goals",
        *_organizer_columns(),
        sa.Column("area_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("kind", sa.String(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("archived_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["area_id"], ["areas.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("length(trim(title)) > 0", name="goal_title_present"),
        sa.CheckConstraint(
            "kind IN ('outcome', 'skill', 'habit', 'project', 'academic', 'personal')",
            name="goal_kind_valid",
        ),
        sa.CheckConstraint(
            "state IN ('active', 'paused', 'achieved', 'retired')",
            name="goal_state_valid",
        ),
    )
    op.create_table(
        "projects",
        *_organizer_columns(),
        sa.Column("goal_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("completed_at", sa.String(), nullable=True),
        sa.Column("archived_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("length(trim(title)) > 0", name="project_title_present"),
        sa.CheckConstraint(
            "state IN ('idea', 'exploring', 'planned', 'active', 'paused', "
            "'completed', 'archived', 'abandoned')",
            name="project_state_valid",
        ),
    )
    op.create_table(
        "milestones",
        *_organizer_columns(),
        sa.Column("goal_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("target_date", sa.String(), nullable=True),
        sa.Column("achieved_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("length(trim(title)) > 0", name="milestone_title_present"),
        sa.CheckConstraint(
            "state IN ('planned', 'in_progress', 'achieved', 'skipped')",
            name="milestone_state_valid",
        ),
    )
    op.create_table(
        "project_milestones",
        *_organizer_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("target_date", sa.String(), nullable=True),
        sa.Column("achieved_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.CheckConstraint(
            "length(trim(title)) > 0", name="project_milestone_title_present"
        ),
        sa.CheckConstraint(
            "state IN ('planned', 'in_progress', 'achieved', 'skipped')",
            name="project_milestone_state_valid",
        ),
    )
    op.create_table(
        "tasks",
        *_organizer_columns(),
        sa.Column("project_id", sa.String(length=36), nullable=True),
        sa.Column("goal_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("details", sa.Text(), nullable=True),
        sa.Column("state", sa.String(), nullable=False, server_default="open"),
        sa.Column("source_kind", sa.String(), nullable=False, server_default="human"),
        sa.Column("importance", sa.String(), nullable=True),
        sa.Column("estimated_minutes", sa.Integer(), nullable=True),
        sa.Column("progress_percent", sa.Integer(), nullable=True),
        sa.Column("deadline_kind", sa.String(), nullable=False, server_default="none"),
        sa.Column("deadline_date", sa.String(), nullable=True),
        sa.Column("deadline_at", sa.String(), nullable=True),
        sa.Column("deadline_timezone", sa.String(), nullable=True),
        sa.Column("completion_evidence", sa.Text(), nullable=True),
        sa.Column("completed_at", sa.String(), nullable=True),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["goal_id"], ["goals.id"], ondelete="RESTRICT"),
        sa.CheckConstraint("length(trim(title)) > 0", name="task_title_present"),
        sa.CheckConstraint(
            "state IN ('open', 'in_progress', 'paused', 'completed', 'canceled')",
            name="task_state_valid",
        ),
        sa.CheckConstraint(
            "source_kind IN ('human', 'system')", name="task_source_kind_valid"
        ),
        sa.CheckConstraint(
            "importance IN ('low', 'normal', 'high') OR importance IS NULL",
            name="task_importance_valid",
        ),
        sa.CheckConstraint(
            "estimated_minutes IS NULL OR estimated_minutes >= 0",
            name="task_estimate_valid",
        ),
        sa.CheckConstraint(
            "progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100",
            name="task_progress_valid",
        ),
        sa.CheckConstraint(DEADLINE_UNION_CHECK, name="task_deadline_union_valid"),
        sa.CheckConstraint(COMPLETION_CHECK, name="task_completion_timestamp_valid"),
    )
    op.create_table(
        "audit_events",
        sa.Column("event_id", sa.String(length=36), primary_key=True),
        sa.Column("occurred_at", sa.String(), nullable=False),
        sa.Column("entity_type", sa.String(), nullable=False),
        sa.Column("entity_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("actor_kind", sa.String(), nullable=False),
        sa.Column("authority", sa.String(), nullable=False),
        sa.Column("source", sa.String(), nullable=False),
        sa.Column("from_revision", sa.Integer(), nullable=True),
        sa.Column("to_revision", sa.Integer(), nullable=True),
        sa.Column("command_id", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "actor_kind IN ('human', 'system', 'integration', 'ai')",
            name="audit_actor_valid",
        ),
        sa.CheckConstraint(
            "authority IN ('direct', 'proposed', 'approved', 'automated')",
            name="audit_authority_valid",
        ),
    )
    op.create_index("ix_goals_area_id", "goals", ["area_id"])
    op.create_index("ix_projects_goal_id", "projects", ["goal_id"])
    op.create_index("ix_milestones_goal_id", "milestones", ["goal_id"])
    op.create_index(
        "ix_project_milestones_project_id", "project_milestones", ["project_id"]
    )
    op.create_index("ix_tasks_project_id", "tasks", ["project_id"])
    op.create_index("ix_tasks_goal_id", "tasks", ["goal_id"])
    op.create_index("ix_tasks_active_state", "tasks", ["trashed_at", "state"])
    op.create_index(
        "ix_tasks_deadline_date", "tasks", ["deadline_kind", "deadline_date"]
    )
    op.create_index("ix_tasks_deadline_at", "tasks", ["deadline_kind", "deadline_at"])
    op.create_index(
        "ix_audit_events_entity",
        "audit_events",
        ["entity_type", "entity_id", "occurred_at"],
    )
    op.create_index("ix_audit_events_command", "audit_events", ["command_id"])


def downgrade() -> None:
    for table in (
        "audit_events",
        "tasks",
        "project_milestones",
        "milestones",
        "projects",
        "goals",
        "areas",
    ):
        op.drop_table(table)
