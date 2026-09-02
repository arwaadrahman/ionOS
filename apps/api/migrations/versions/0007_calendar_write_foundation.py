"""Add the Phase 2C-1 Calendar write foundation.

Revision ID: 0007_calendar_write_foundation
Revises: 0006_calendar_presentation_metadata
Create Date: 2026-08-30
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0007_calendar_write_foundation"
down_revision: str | None = "0006_calendar_presentation_metadata"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.batch_alter_table("google_accounts") as batch:
        batch.add_column(
            sa.Column(
                "calendar_write_scope_state",
                sa.String(),
                server_default="read_only",
                nullable=False,
            )
        )
        batch.create_check_constraint(
            "google_account_write_scope_state_valid",
            "calendar_write_scope_state IN "
            "('read_only', 'write_granted', 'reauth_required')",
        )

    with op.batch_alter_table("google_event_links") as batch:
        batch.add_column(
            sa.Column(
                "link_state",
                sa.String(),
                server_default="confirmed",
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column(
                "provider_event_type",
                sa.String(),
                server_default="default",
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column(
                "provider_locked",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch.add_column(
            sa.Column(
                "has_attendees",
                sa.Boolean(),
                server_default=sa.false(),
                nullable=False,
            )
        )
        batch.alter_column(
            "last_seen_sync_generation",
            existing_type=sa.String(length=36),
            nullable=True,
        )
        batch.create_check_constraint(
            "google_event_link_state_valid",
            "link_state IN ('confirmed', 'pending_create')",
        )
        batch.create_check_constraint(
            "google_event_type_valid",
            "provider_event_type IN ('default', 'special', 'unknown')",
        )
        batch.create_check_constraint(
            "google_event_link_confirmation_valid",
            "link_state = 'pending_create' OR last_seen_sync_generation IS NOT NULL",
        )

    op.create_table(
        "calendar_provider_write_intents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("command_id", sa.String(length=36), nullable=False),
        sa.Column("calendar_block_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=36), nullable=False),
        sa.Column("calendar_id", sa.String(length=36), nullable=False),
        sa.Column("provider_event_id", sa.Text(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("predecessor_intent_id", sa.String(length=36), nullable=True),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("recurrence_scope", sa.String(), nullable=False),
        sa.Column("changed_fields_json", sa.Text(), nullable=False),
        sa.Column("base_values_json", sa.Text(), nullable=True),
        sa.Column("desired_values_json", sa.Text(), nullable=True),
        sa.Column("expected_provider_etag", sa.Text(), nullable=True),
        sa.Column("source_block_revision", sa.Integer(), nullable=False),
        sa.Column("schema_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("state", sa.String(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("next_attempt_at", sa.String(), nullable=True),
        sa.Column("last_attempt_at", sa.String(), nullable=True),
        sa.Column("failure_class", sa.String(), nullable=True),
        sa.Column("failure_reason", sa.String(), nullable=True),
        sa.Column("created_at", sa.String(), nullable=False),
        sa.Column("updated_at", sa.String(), nullable=False),
        sa.Column("resolved_at", sa.String(), nullable=True),
        sa.Column("prune_after", sa.String(), nullable=True),
        sa.Column("provenance", sa.String(), nullable=False),
        sa.CheckConstraint("sequence >= 1", name="calendar_write_sequence_positive"),
        sa.CheckConstraint(
            "operation IN ('create', 'patch', 'cancel_occurrence', "
            "'delete_event', 'delete_series')",
            name="calendar_write_operation_valid",
        ),
        sa.CheckConstraint(
            "recurrence_scope IN ('single', 'occurrence', 'series')",
            name="calendar_write_recurrence_scope_valid",
        ),
        sa.CheckConstraint(
            "length(changed_fields_json) BETWEEN 2 AND 4096",
            name="calendar_write_field_mask_bounded",
        ),
        sa.CheckConstraint(
            "base_values_json IS NULL OR length(base_values_json) <= 524288",
            name="calendar_write_base_values_bounded",
        ),
        sa.CheckConstraint(
            "desired_values_json IS NULL OR length(desired_values_json) <= 524288",
            name="calendar_write_desired_values_bounded",
        ),
        sa.CheckConstraint(
            "source_block_revision >= 1", name="calendar_write_revision_positive"
        ),
        sa.CheckConstraint(
            "schema_version = 1", name="calendar_write_schema_version_valid"
        ),
        sa.CheckConstraint(
            "state IN ('queued', 'ready', 'attempting', 'retry_wait', "
            "'reauth_required', 'conflict', 'ambiguous', 'failed', "
            "'completed', 'cancelled')",
            name="calendar_write_state_valid",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 5",
            name="calendar_write_attempt_count_bounded",
        ),
        sa.CheckConstraint(
            "state <> 'retry_wait' OR next_attempt_at IS NOT NULL",
            name="calendar_write_retry_timestamp_required",
        ),
        sa.CheckConstraint(
            "failure_class IS NULL OR failure_class IN "
            "('success', 'retryable_transport', 'retryable_backend', "
            "'retryable_quota', 'reauthentication_required', "
            "'stale_precondition', 'duplicate_or_ambiguous_create', "
            "'provider_not_found', 'invalid_target', "
            "'terminal_provider_rejection')",
            name="calendar_write_failure_class_valid",
        ),
        sa.CheckConstraint(
            "failure_reason IS NULL OR length(failure_reason) <= 128",
            name="calendar_write_failure_reason_bounded",
        ),
        sa.CheckConstraint(
            "provenance = 'direct_human'",
            name="calendar_write_provenance_valid",
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
        sa.ForeignKeyConstraint(
            ["predecessor_intent_id"],
            ["calendar_provider_write_intents.id"],
            ondelete="SET NULL",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("command_id", name="uq_calendar_write_command"),
        sa.UniqueConstraint(
            "calendar_block_id",
            "sequence",
            name="uq_calendar_write_block_sequence",
        ),
    )
    op.create_index(
        "ix_calendar_write_ready",
        "calendar_provider_write_intents",
        ["state", "next_attempt_at", "created_at"],
    )
    op.create_index(
        "ix_calendar_write_account_state",
        "calendar_provider_write_intents",
        ["account_id", "state"],
    )
    op.create_index(
        "ix_calendar_write_block",
        "calendar_provider_write_intents",
        ["calendar_block_id", "sequence"],
    )
    op.create_index(
        "ix_calendar_write_prune",
        "calendar_provider_write_intents",
        ["state", "prune_after"],
    )

    op.create_table(
        "calendar_provider_write_audit",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("intent_id", sa.String(length=36), nullable=False),
        sa.Column("calendar_block_id", sa.String(length=36), nullable=False),
        sa.Column("action", sa.String(), nullable=False),
        sa.Column("operation", sa.String(), nullable=False),
        sa.Column("changed_fields_json", sa.Text(), nullable=False),
        sa.Column("attempt_count", sa.Integer(), nullable=False),
        sa.Column("safe_reason_class", sa.String(), nullable=True),
        sa.Column("safe_reason", sa.String(), nullable=True),
        sa.Column("from_state", sa.String(), nullable=True),
        sa.Column("to_state", sa.String(), nullable=False),
        sa.Column("source_revision", sa.Integer(), nullable=True),
        sa.Column("resulting_revision", sa.Integer(), nullable=True),
        sa.Column("occurred_at", sa.String(), nullable=False),
        sa.Column("executor_provenance", sa.String(), nullable=False),
        sa.CheckConstraint(
            "action IN ('write_intent_queued', 'write_intent_ready', "
            "'write_attempt_started', 'write_retry_scheduled', "
            "'write_reauthentication_required', 'write_outcome_ambiguous', "
            "'write_conflict_detected', 'write_failed_terminally', "
            "'write_completed', 'write_cancelled')",
            name="calendar_write_audit_action_valid",
        ),
        sa.CheckConstraint(
            "operation IN ('create', 'patch', 'cancel_occurrence', "
            "'delete_event', 'delete_series')",
            name="calendar_write_audit_operation_valid",
        ),
        sa.CheckConstraint(
            "(from_state IS NULL OR from_state IN "
            "('queued', 'ready', 'attempting', 'retry_wait', "
            "'reauth_required', 'conflict', 'ambiguous', 'failed', "
            "'completed', 'cancelled')) AND to_state IN "
            "('queued', 'ready', 'attempting', 'retry_wait', "
            "'reauth_required', 'conflict', 'ambiguous', 'failed', "
            "'completed', 'cancelled')",
            name="calendar_write_audit_state_valid",
        ),
        sa.CheckConstraint(
            "length(changed_fields_json) BETWEEN 2 AND 4096",
            name="calendar_write_audit_fields_bounded",
        ),
        sa.CheckConstraint(
            "attempt_count BETWEEN 0 AND 5",
            name="calendar_write_audit_attempt_bounded",
        ),
        sa.CheckConstraint(
            "safe_reason IS NULL OR length(safe_reason) <= 128",
            name="calendar_write_audit_reason_bounded",
        ),
        sa.CheckConstraint(
            "safe_reason_class IS NULL OR safe_reason_class IN "
            "('success', 'retryable_transport', 'retryable_backend', "
            "'retryable_quota', 'reauthentication_required', "
            "'stale_precondition', 'duplicate_or_ambiguous_create', "
            "'provider_not_found', 'invalid_target', "
            "'terminal_provider_rejection')",
            name="calendar_write_audit_reason_class_valid",
        ),
        sa.CheckConstraint(
            "executor_provenance IN ('direct_human', 'recovery')",
            name="calendar_write_audit_provenance_valid",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_calendar_write_audit_intent",
        "calendar_provider_write_audit",
        ["intent_id", "occurred_at"],
    )
    op.create_index(
        "ix_calendar_write_audit_block",
        "calendar_provider_write_audit",
        ["calendar_block_id", "occurred_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_calendar_write_audit_block", table_name="calendar_provider_write_audit"
    )
    op.drop_index(
        "ix_calendar_write_audit_intent", table_name="calendar_provider_write_audit"
    )
    op.drop_table("calendar_provider_write_audit")
    op.drop_index(
        "ix_calendar_write_prune", table_name="calendar_provider_write_intents"
    )
    op.drop_index(
        "ix_calendar_write_block", table_name="calendar_provider_write_intents"
    )
    op.drop_index(
        "ix_calendar_write_account_state",
        table_name="calendar_provider_write_intents",
    )
    op.drop_index(
        "ix_calendar_write_ready", table_name="calendar_provider_write_intents"
    )
    op.drop_table("calendar_provider_write_intents")

    with op.batch_alter_table("google_event_links") as batch:
        batch.drop_constraint("google_event_link_confirmation_valid", type_="check")
        batch.drop_constraint("google_event_type_valid", type_="check")
        batch.drop_constraint("google_event_link_state_valid", type_="check")
        batch.alter_column(
            "last_seen_sync_generation",
            existing_type=sa.String(length=36),
            nullable=False,
        )
        batch.drop_column("has_attendees")
        batch.drop_column("provider_locked")
        batch.drop_column("provider_event_type")
        batch.drop_column("link_state")

    with op.batch_alter_table("google_accounts") as batch:
        batch.drop_constraint("google_account_write_scope_state_valid", type_="check")
        batch.drop_column("calendar_write_scope_state")
