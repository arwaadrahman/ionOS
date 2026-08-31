"""Add narrow Ion-owned Calendar presentation metadata.

Revision ID: 0006_calendar_presentation_metadata
Revises: 0005_google_calendar_foundation
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0006_calendar_presentation_metadata"
down_revision: str | None = "0005_google_calendar_foundation"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("google_calendars") as batch:
        batch.add_column(
            sa.Column(
                "hidden_in_ion",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
    with op.batch_alter_table("calendar_block_ion_metadata") as batch:
        batch.add_column(sa.Column("category", sa.String(), nullable=True))
        batch.add_column(sa.Column("category_subtype", sa.String(), nullable=True))
        batch.create_check_constraint(
            "calendar_block_category_valid",
            "category IS NULL OR category IN "
            "('academic', 'career', 'personal_project', 'routine_physical', "
            "'personal', 'fun', 'ion_focus')",
        )
        batch.create_check_constraint(
            "calendar_block_category_subtype_valid",
            "category_subtype IS NULL OR (category IS NOT NULL "
            "AND length(category_subtype) BETWEEN 1 AND 64 "
            "AND category_subtype NOT GLOB '*[^a-z0-9_]*' "
            "AND category_subtype GLOB '[a-z]*')",
        )


def downgrade() -> None:
    with op.batch_alter_table("calendar_block_ion_metadata") as batch:
        batch.drop_constraint("calendar_block_category_subtype_valid", type_="check")
        batch.drop_constraint("calendar_block_category_valid", type_="check")
        batch.drop_column("category_subtype")
        batch.drop_column("category")
    with op.batch_alter_table("google_calendars") as batch:
        batch.drop_column("hidden_in_ion")
