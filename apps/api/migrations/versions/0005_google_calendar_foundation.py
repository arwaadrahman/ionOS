"""Add the Phase 2A Google Calendar read-sync foundation.

Revision ID: 0005_google_calendar_foundation
Revises: 0004_today_planning
Create Date: 2026-08-29
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0005_google_calendar_foundation"
down_revision: str | None = "0004_today_planning"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "google_accounts",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("provider_account_id", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("granted_scopes", sa.Text(), nullable=False),
        sa.Column("keychain_locator", sa.Text(), nullable=False),
        sa.Column("auth_state", sa.String(), nullable=False),
        sa.Column("last_auth_at", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "auth_state IN ('connected', 'reauth_required', 'disconnected')",
            name="google_account_auth_state_valid",
        ),
        sa.CheckConstraint("revision >= 1", name="google_account_revision_positive"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "provider_account_id", name="uq_google_account_provider_id"
        ),
        sa.UniqueConstraint(
            "keychain_locator", name="uq_google_account_keychain_locator"
        ),
    )

    op.create_table(
        "google_calendars",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("provider_calendar_id", sa.Text(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("timezone", sa.Text(), nullable=True),
        sa.Column("access_role", sa.String(), nullable=False),
        sa.Column("provider_etag", sa.Text(), nullable=True),
        sa.Column(
            "is_primary", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "provider_selected", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "provider_hidden", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "enabled_in_ion", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column(
            "provider_deleted", sa.Boolean(), server_default=sa.false(), nullable=False
        ),
        sa.Column("next_sync_token", sa.Text(), nullable=True),
        sa.Column("sync_state", sa.String(), nullable=False),
        sa.Column("active_sync_generation", sa.String(length=36), nullable=True),
        sa.Column("active_sync_mode", sa.String(), nullable=True),
        sa.Column("last_synced_at", sa.String(), nullable=True),
        sa.Column("last_error_code", sa.String(), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_retry_at", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "access_role IN ('none', 'freeBusyReader', 'reader', "
            "'writerWithoutPrivateAccess', 'writer', 'owner')",
            name="google_calendar_access_role_valid",
        ),
        sa.CheckConstraint(
            "sync_state IN ('idle', 'syncing', 'retry_wait', 'failed', "
            "'reauth_required', 'disconnected')",
            name="google_calendar_sync_state_valid",
        ),
        sa.CheckConstraint(
            "active_sync_mode IN ('full', 'incremental') OR active_sync_mode IS NULL",
            name="google_calendar_sync_mode_valid",
        ),
        sa.CheckConstraint(
            "retry_count >= 0", name="google_calendar_retry_nonnegative"
        ),
        sa.CheckConstraint("revision >= 1", name="google_calendar_revision_positive"),
        sa.ForeignKeyConstraint(
            ["account_id"], ["google_accounts.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "account_id",
            "provider_calendar_id",
            name="uq_google_calendar_account_provider_id",
        ),
    )
    op.create_index("ix_google_calendars_account", "google_calendars", ["account_id"])

    op.create_table(
        "calendar_blocks",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("source_kind", sa.String(), nullable=False),
        sa.Column("title", sa.Text(), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("location", sa.Text(), nullable=True),
        sa.Column("temporal_kind", sa.String(), nullable=False),
        sa.Column("start_date", sa.String(), nullable=True),
        sa.Column("end_date", sa.String(), nullable=True),
        sa.Column("start_at", sa.String(), nullable=True),
        sa.Column("end_at", sa.String(), nullable=True),
        sa.Column("start_timezone", sa.Text(), nullable=True),
        sa.Column("end_timezone", sa.Text(), nullable=True),
        sa.Column("status", sa.String(), nullable=False),
        sa.Column("transparency", sa.String(), nullable=False),
        sa.Column("recurrence_kind", sa.String(), nullable=False),
        sa.Column("recurrence_rules", sa.Text(), nullable=True),
        sa.Column("recurrence_master_block_id", sa.String(length=36), nullable=True),
        sa.Column("provider_deleted_at", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.Column("trashed_at", sa.String(), nullable=True),
        sa.CheckConstraint(
            "source_kind IN ('google', 'ion')", name="calendar_block_source_valid"
        ),
        sa.CheckConstraint(
            "length(trim(title)) > 0", name="calendar_block_title_present"
        ),
        sa.CheckConstraint(
            "temporal_kind IN ('all_day', 'timed')",
            name="calendar_block_temporal_kind_valid",
        ),
        sa.CheckConstraint(
            "(temporal_kind = 'all_day' AND start_date IS NOT NULL "
            "AND end_date IS NOT NULL "
            "AND start_at IS NULL AND end_at IS NULL AND start_timezone IS NULL "
            "AND end_timezone IS NULL) OR "
            "(temporal_kind = 'timed' AND start_date IS NULL AND end_date IS NULL "
            "AND start_at IS NOT NULL AND end_at IS NOT NULL "
            "AND start_timezone IS NOT NULL "
            "AND end_timezone IS NOT NULL)",
            name="calendar_block_temporal_union_valid",
        ),
        sa.CheckConstraint(
            "status IN ('confirmed', 'tentative', 'cancelled')",
            name="calendar_block_status_valid",
        ),
        sa.CheckConstraint(
            "transparency IN ('opaque', 'transparent')",
            name="calendar_block_transparency_valid",
        ),
        sa.CheckConstraint(
            "recurrence_kind IN ('single', 'master', 'exception')",
            name="calendar_block_recurrence_kind_valid",
        ),
        sa.CheckConstraint("revision >= 1", name="calendar_block_revision_positive"),
        sa.ForeignKeyConstraint(
            ["recurrence_master_block_id"], ["calendar_blocks.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_calendar_blocks_time", "calendar_blocks", ["start_at", "start_date"]
    )

    op.create_table(
        "calendar_block_ion_metadata",
        sa.Column("calendar_block_id", sa.String(length=36), nullable=False),
        sa.Column("flexibility", sa.String(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default="1", nullable=False),
        sa.CheckConstraint(
            "flexibility IN ('locked', 'flexible', 'ion_controlled')",
            name="calendar_block_flexibility_valid",
        ),
        sa.CheckConstraint(
            "revision >= 1", name="calendar_block_metadata_revision_positive"
        ),
        sa.ForeignKeyConstraint(
            ["calendar_block_id"], ["calendar_blocks.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("calendar_block_id"),
    )

    op.create_table(
        "google_event_links",
        sa.Column("calendar_block_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("calendar_id", sa.String(length=36), nullable=False),
        sa.Column("provider_event_id", sa.Text(), nullable=False),
        sa.Column("ical_uid", sa.Text(), nullable=True),
        sa.Column("provider_etag", sa.Text(), nullable=True),
        sa.Column("provider_updated_at", sa.String(), nullable=True),
        sa.Column("recurring_event_id", sa.Text(), nullable=True),
        sa.Column("original_start_kind", sa.String(), nullable=False),
        sa.Column("original_start_date", sa.String(), nullable=True),
        sa.Column("original_start_at", sa.String(), nullable=True),
        sa.Column("original_start_timezone", sa.Text(), nullable=True),
        sa.Column("last_seen_sync_generation", sa.String(length=36), nullable=False),
        sa.CheckConstraint(
            "(original_start_kind = 'none' AND original_start_date IS NULL "
            "AND original_start_at IS NULL AND original_start_timezone IS NULL) OR "
            "(original_start_kind = 'date' AND original_start_date IS NOT NULL "
            "AND original_start_at IS NULL AND original_start_timezone IS NULL) OR "
            "(original_start_kind = 'instant' AND original_start_date IS NULL "
            "AND original_start_at IS NOT NULL "
            "AND original_start_timezone IS NOT NULL)",
            name="google_event_original_start_union_valid",
        ),
        sa.ForeignKeyConstraint(
            ["calendar_block_id"], ["calendar_blocks.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["account_id"], ["google_accounts.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["calendar_id"], ["google_calendars.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("calendar_block_id"),
        sa.UniqueConstraint(
            "calendar_id", "provider_event_id", name="uq_google_event_calendar_event_id"
        ),
    )
    op.create_index("ix_google_event_ical_uid", "google_event_links", ["ical_uid"])
    op.create_index(
        "ix_google_event_recurring_event_id",
        "google_event_links",
        ["calendar_id", "recurring_event_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_google_event_recurring_event_id", table_name="google_event_links")
    op.drop_index("ix_google_event_ical_uid", table_name="google_event_links")
    op.drop_table("google_event_links")
    op.drop_table("calendar_block_ion_metadata")
    op.drop_index("ix_calendar_blocks_time", table_name="calendar_blocks")
    op.drop_table("calendar_blocks")
    op.drop_index("ix_google_calendars_account", table_name="google_calendars")
    op.drop_table("google_calendars")
    op.drop_table("google_accounts")
