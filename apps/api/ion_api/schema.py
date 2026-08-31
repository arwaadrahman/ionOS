"""SQLAlchemy Core definitions for the Phase 1A organizer foundation."""

from sqlalchemy import (
    CheckConstraint,
    Column,
    ForeignKey,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
)

metadata = MetaData()
DEADLINE_UNION_CHECK = (
    "(deadline_kind = 'none' AND deadline_date IS NULL AND deadline_at IS NULL "
    "AND deadline_timezone IS NULL) OR "
    "(deadline_kind = 'date' AND deadline_date IS NOT NULL AND deadline_at IS NULL "
    "AND deadline_timezone IS NULL) OR "
    "(deadline_kind = 'instant' AND deadline_date IS NULL AND deadline_at IS NOT NULL "
    "AND deadline_timezone IS NOT NULL)"
)


def organizer_columns() -> list[Column]:
    return [
        Column("id", String(36), primary_key=True),
        Column("created_at", String, nullable=False),
        Column("updated_at", String, nullable=False),
        Column("revision", Integer, nullable=False, server_default="1"),
        Column("trashed_at", String, nullable=True),
        CheckConstraint("revision >= 1", name="revision_positive"),
    ]


areas = Table(
    "areas",
    metadata,
    *organizer_columns(),
    Column("name", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("archived_at", String, nullable=True),
    CheckConstraint("length(trim(name)) > 0", name="area_name_present"),
)

goals = Table(
    "goals",
    metadata,
    *organizer_columns(),
    Column("area_id", String(36), ForeignKey("areas.id", ondelete="RESTRICT")),
    Column("title", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("kind", String, nullable=False),
    Column("state", String, nullable=False),
    Column("archived_at", String, nullable=True),
    CheckConstraint("length(trim(title)) > 0", name="goal_title_present"),
    CheckConstraint(
        "kind IN ('outcome', 'skill', 'habit', 'project', 'academic', 'personal')",
        name="goal_kind_valid",
    ),
    CheckConstraint(
        "state IN ('active', 'paused', 'achieved', 'retired')",
        name="goal_state_valid",
    ),
)

milestones = Table(
    "milestones",
    metadata,
    *organizer_columns(),
    Column(
        "goal_id",
        String(36),
        ForeignKey("goals.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("title", Text, nullable=False),
    Column("state", String, nullable=False),
    Column("target_date", String, nullable=True),
    Column("achieved_at", String, nullable=True),
    Column("position", Integer, nullable=False),
    CheckConstraint("length(trim(title)) > 0", name="milestone_title_present"),
    CheckConstraint(
        "state IN ('planned', 'in_progress', 'achieved', 'skipped')",
        name="milestone_state_valid",
    ),
    CheckConstraint("position >= 0", name="milestone_position_nonnegative"),
    UniqueConstraint("goal_id", "position", name="uq_milestones_goal_position"),
)

projects = Table(
    "projects",
    metadata,
    *organizer_columns(),
    Column("goal_id", String(36), ForeignKey("goals.id", ondelete="RESTRICT")),
    Column("title", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("state", String, nullable=False),
    Column("completed_at", String, nullable=True),
    Column("archived_at", String, nullable=True),
    CheckConstraint("length(trim(title)) > 0", name="project_title_present"),
    CheckConstraint(
        "state IN ('idea', 'exploring', 'planned', 'active', 'paused', "
        "'completed', 'archived', 'abandoned')",
        name="project_state_valid",
    ),
)

project_milestones = Table(
    "project_milestones",
    metadata,
    *organizer_columns(),
    Column(
        "project_id",
        String(36),
        ForeignKey("projects.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("title", Text, nullable=False),
    Column("state", String, nullable=False),
    Column("target_date", String, nullable=True),
    Column("achieved_at", String, nullable=True),
    Column("position", Integer, nullable=False),
    CheckConstraint("length(trim(title)) > 0", name="project_milestone_title_present"),
    CheckConstraint(
        "state IN ('planned', 'in_progress', 'achieved', 'skipped')",
        name="project_milestone_state_valid",
    ),
    CheckConstraint("position >= 0", name="project_milestone_position_nonnegative"),
    UniqueConstraint(
        "project_id", "position", name="uq_project_milestones_project_position"
    ),
)

tasks = Table(
    "tasks",
    metadata,
    *organizer_columns(),
    Column("project_id", String(36), ForeignKey("projects.id", ondelete="RESTRICT")),
    Column("goal_id", String(36), ForeignKey("goals.id", ondelete="RESTRICT")),
    Column("title", Text, nullable=False),
    Column("details", Text, nullable=True),
    Column("state", String, nullable=False, server_default="open"),
    Column("source_kind", String, nullable=False, server_default="human"),
    Column("importance", String, nullable=True),
    Column("estimated_minutes", Integer, nullable=True),
    Column("progress_percent", Integer, nullable=True),
    Column("deadline_kind", String, nullable=False, server_default="none"),
    Column("deadline_date", String, nullable=True),
    Column("deadline_at", String, nullable=True),
    Column("deadline_timezone", String, nullable=True),
    Column("completion_evidence", Text, nullable=True),
    Column("completed_at", String, nullable=True),
    CheckConstraint("length(trim(title)) > 0", name="task_title_present"),
    CheckConstraint(
        "state IN ('open', 'in_progress', 'paused', 'completed', 'canceled')",
        name="task_state_valid",
    ),
    CheckConstraint(
        "source_kind IN ('human', 'system')", name="task_source_kind_valid"
    ),
    CheckConstraint(
        "importance IN ('low', 'normal', 'high') OR importance IS NULL",
        name="task_importance_valid",
    ),
    CheckConstraint(
        "estimated_minutes IS NULL OR estimated_minutes >= 0",
        name="task_estimate_valid",
    ),
    CheckConstraint(
        "progress_percent IS NULL OR progress_percent BETWEEN 0 AND 100",
        name="task_progress_valid",
    ),
    CheckConstraint(DEADLINE_UNION_CHECK, name="task_deadline_union_valid"),
    CheckConstraint(
        "(state = 'completed' AND completed_at IS NOT NULL) OR "
        "(state <> 'completed' AND completed_at IS NULL)",
        name="task_completion_timestamp_valid",
    ),
)

audit_events = Table(
    "audit_events",
    metadata,
    Column("event_id", String(36), primary_key=True),
    Column("occurred_at", String, nullable=False),
    Column("entity_type", String, nullable=False),
    Column("entity_id", String(36), nullable=False),
    Column("action", String, nullable=False),
    Column("actor_kind", String, nullable=False),
    Column("authority", String, nullable=False),
    Column("source", String, nullable=False),
    Column("from_revision", Integer, nullable=True),
    Column("to_revision", Integer, nullable=True),
    Column("command_id", String(36), nullable=False),
    CheckConstraint(
        "actor_kind IN ('human', 'system', 'integration', 'ai')",
        name="audit_actor_valid",
    ),
    CheckConstraint(
        "authority IN ('direct', 'proposed', 'approved', 'automated')",
        name="audit_authority_valid",
    ),
)

task_day_plans = Table(
    "task_day_plans",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "task_id",
        String(36),
        ForeignKey("tasks.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("planning_date", String, nullable=False),
    Column("role", String, nullable=False),
    Column("position", Integer, nullable=False),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("revision", Integer, nullable=False, server_default="1"),
    CheckConstraint(
        "length(planning_date) = 10 AND "
        "planning_date GLOB '[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]'",
        name="task_day_plan_date_shape_valid",
    ),
    CheckConstraint(
        "role IN ('priority', 'planned', 'backup')",
        name="task_day_plan_role_valid",
    ),
    CheckConstraint("position >= 0", name="task_day_plan_position_nonnegative"),
    CheckConstraint("revision >= 1", name="task_day_plan_revision_positive"),
    UniqueConstraint("task_id", "planning_date", name="uq_task_day_plans_task_date"),
    UniqueConstraint(
        "planning_date",
        "role",
        "position",
        name="uq_task_day_plans_date_role_position",
    ),
)

google_accounts = Table(
    "google_accounts",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("provider_account_id", Text, nullable=False, unique=True),
    Column("display_name", Text, nullable=False),
    Column("granted_scopes", Text, nullable=False),
    Column("keychain_locator", Text, nullable=False, unique=True),
    Column("auth_state", String, nullable=False),
    Column(
        "calendar_write_scope_state",
        String,
        nullable=False,
        server_default="read_only",
    ),
    Column("last_auth_at", String, nullable=True),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("revision", Integer, nullable=False, server_default="1"),
    CheckConstraint(
        "auth_state IN ('connected', 'reauth_required', 'disconnected')",
        name="google_account_auth_state_valid",
    ),
    CheckConstraint(
        "calendar_write_scope_state IN "
        "('read_only', 'write_granted', 'reauth_required')",
        name="google_account_write_scope_state_valid",
    ),
    CheckConstraint("revision >= 1", name="google_account_revision_positive"),
)

google_calendars = Table(
    "google_calendars",
    metadata,
    Column("id", String(36), primary_key=True),
    Column(
        "account_id",
        String(36),
        ForeignKey("google_accounts.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    ),
    Column("provider_calendar_id", Text, nullable=False),
    Column("summary", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("location", Text, nullable=True),
    Column("timezone", Text, nullable=True),
    Column("access_role", String, nullable=False),
    Column("provider_etag", Text, nullable=True),
    Column("is_primary", Integer, nullable=False, server_default="0"),
    Column("provider_selected", Integer, nullable=False, server_default="0"),
    Column("provider_hidden", Integer, nullable=False, server_default="0"),
    Column("enabled_in_ion", Integer, nullable=False, server_default="0"),
    Column("hidden_in_ion", Integer, nullable=False, server_default="0"),
    Column("provider_deleted", Integer, nullable=False, server_default="0"),
    Column("next_sync_token", Text, nullable=True),
    Column("sync_state", String, nullable=False),
    Column("active_sync_generation", String(36), nullable=True),
    Column("active_sync_mode", String, nullable=True),
    Column("last_synced_at", String, nullable=True),
    Column("last_error_code", String, nullable=True),
    Column("retry_count", Integer, nullable=False, server_default="0"),
    Column("next_retry_at", String, nullable=True),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("revision", Integer, nullable=False, server_default="1"),
    CheckConstraint(
        "access_role IN ('none', 'freeBusyReader', 'reader', "
        "'writerWithoutPrivateAccess', 'writer', 'owner')",
        name="google_calendar_access_role_valid",
    ),
    CheckConstraint(
        "sync_state IN ('idle', 'syncing', 'retry_wait', 'failed', "
        "'reauth_required', 'disconnected')",
        name="google_calendar_sync_state_valid",
    ),
    CheckConstraint(
        "active_sync_mode IN ('full', 'incremental') OR active_sync_mode IS NULL",
        name="google_calendar_sync_mode_valid",
    ),
    CheckConstraint("retry_count >= 0", name="google_calendar_retry_nonnegative"),
    CheckConstraint("revision >= 1", name="google_calendar_revision_positive"),
    UniqueConstraint(
        "account_id",
        "provider_calendar_id",
        name="uq_google_calendar_account_provider_id",
    ),
)

calendar_blocks = Table(
    "calendar_blocks",
    metadata,
    *organizer_columns(),
    Column("source_kind", String, nullable=False),
    Column("title", Text, nullable=False),
    Column("description", Text, nullable=True),
    Column("location", Text, nullable=True),
    Column("temporal_kind", String, nullable=False),
    Column("start_date", String, nullable=True),
    Column("end_date", String, nullable=True),
    Column("start_at", String, nullable=True),
    Column("end_at", String, nullable=True),
    Column("start_timezone", Text, nullable=True),
    Column("end_timezone", Text, nullable=True),
    Column("status", String, nullable=False),
    Column("transparency", String, nullable=False),
    Column("recurrence_kind", String, nullable=False),
    Column("recurrence_rules", Text, nullable=True),
    Column(
        "recurrence_master_block_id",
        String(36),
        ForeignKey("calendar_blocks.id", ondelete="RESTRICT"),
        nullable=True,
    ),
    Column("provider_deleted_at", String, nullable=True),
    CheckConstraint(
        "source_kind IN ('google', 'ion')", name="calendar_block_source_valid"
    ),
    CheckConstraint("length(trim(title)) > 0", name="calendar_block_title_present"),
    CheckConstraint(
        "temporal_kind IN ('all_day', 'timed')",
        name="calendar_block_temporal_kind_valid",
    ),
    CheckConstraint(
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
    CheckConstraint(
        "status IN ('confirmed', 'tentative', 'cancelled')",
        name="calendar_block_status_valid",
    ),
    CheckConstraint(
        "transparency IN ('opaque', 'transparent')",
        name="calendar_block_transparency_valid",
    ),
    CheckConstraint(
        "recurrence_kind IN ('single', 'master', 'exception')",
        name="calendar_block_recurrence_kind_valid",
    ),
)

calendar_block_ion_metadata = Table(
    "calendar_block_ion_metadata",
    metadata,
    Column(
        "calendar_block_id",
        String(36),
        ForeignKey("calendar_blocks.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column("flexibility", String, nullable=False),
    Column("notes", Text, nullable=True),
    Column("category", String, nullable=True),
    Column("category_subtype", String, nullable=True),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("revision", Integer, nullable=False, server_default="1"),
    CheckConstraint(
        "flexibility IN ('locked', 'flexible', 'ion_controlled')",
        name="calendar_block_flexibility_valid",
    ),
    CheckConstraint(
        "category IS NULL OR category IN "
        "('academic', 'career', 'personal_project', 'routine_physical', "
        "'personal', 'fun', 'ion_focus')",
        name="calendar_block_category_valid",
    ),
    CheckConstraint(
        "category_subtype IS NULL OR (category IS NOT NULL "
        "AND length(category_subtype) BETWEEN 1 AND 64 "
        "AND category_subtype NOT GLOB '*[^a-z0-9_]*' "
        "AND category_subtype GLOB '[a-z]*')",
        name="calendar_block_category_subtype_valid",
    ),
    CheckConstraint("revision >= 1", name="calendar_block_metadata_revision_positive"),
)

google_event_links = Table(
    "google_event_links",
    metadata,
    Column(
        "calendar_block_id",
        String(36),
        ForeignKey("calendar_blocks.id", ondelete="RESTRICT"),
        primary_key=True,
    ),
    Column(
        "account_id",
        String(36),
        ForeignKey("google_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "calendar_id",
        String(36),
        ForeignKey("google_calendars.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("provider_event_id", Text, nullable=False),
    Column("ical_uid", Text, nullable=True, index=True),
    Column("provider_etag", Text, nullable=True),
    Column("provider_updated_at", String, nullable=True),
    Column("recurring_event_id", Text, nullable=True),
    Column("original_start_kind", String, nullable=False),
    Column("original_start_date", String, nullable=True),
    Column("original_start_at", String, nullable=True),
    Column("original_start_timezone", Text, nullable=True),
    Column("last_seen_sync_generation", String(36), nullable=True),
    Column("link_state", String, nullable=False, server_default="confirmed"),
    Column("provider_event_type", String, nullable=False, server_default="default"),
    Column("provider_locked", Integer, nullable=False, server_default="0"),
    Column("has_attendees", Integer, nullable=False, server_default="0"),
    CheckConstraint(
        "(original_start_kind = 'none' AND original_start_date IS NULL "
        "AND original_start_at IS NULL AND original_start_timezone IS NULL) OR "
        "(original_start_kind = 'date' AND original_start_date IS NOT NULL "
        "AND original_start_at IS NULL AND original_start_timezone IS NULL) OR "
        "(original_start_kind = 'instant' AND original_start_date IS NULL "
        "AND original_start_at IS NOT NULL AND original_start_timezone IS NOT NULL)",
        name="google_event_original_start_union_valid",
    ),
    CheckConstraint(
        "link_state IN ('confirmed', 'pending_create')",
        name="google_event_link_state_valid",
    ),
    CheckConstraint(
        "provider_event_type IN ('default', 'special', 'unknown')",
        name="google_event_type_valid",
    ),
    CheckConstraint(
        "link_state = 'pending_create' OR last_seen_sync_generation IS NOT NULL",
        name="google_event_link_confirmation_valid",
    ),
    UniqueConstraint(
        "calendar_id", "provider_event_id", name="uq_google_event_calendar_event_id"
    ),
)

calendar_provider_write_intents = Table(
    "calendar_provider_write_intents",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("command_id", String(36), nullable=False, unique=True),
    Column(
        "calendar_block_id",
        String(36),
        ForeignKey("calendar_blocks.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "account_id",
        String(36),
        ForeignKey("google_accounts.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column(
        "calendar_id",
        String(36),
        ForeignKey("google_calendars.id", ondelete="RESTRICT"),
        nullable=False,
    ),
    Column("provider_event_id", Text, nullable=False),
    Column("sequence", Integer, nullable=False),
    Column(
        "predecessor_intent_id",
        String(36),
        ForeignKey("calendar_provider_write_intents.id", ondelete="SET NULL"),
        nullable=True,
    ),
    Column("operation", String, nullable=False),
    Column("recurrence_scope", String, nullable=False),
    Column("changed_fields_json", Text, nullable=False),
    Column("base_values_json", Text, nullable=True),
    Column("desired_values_json", Text, nullable=True),
    Column("expected_provider_etag", Text, nullable=True),
    Column("source_block_revision", Integer, nullable=False),
    Column("schema_version", Integer, nullable=False, server_default="1"),
    Column("state", String, nullable=False, index=True),
    Column("attempt_count", Integer, nullable=False, server_default="0"),
    Column("next_attempt_at", String, nullable=True),
    Column("last_attempt_at", String, nullable=True),
    Column("failure_class", String, nullable=True),
    Column("failure_reason", String, nullable=True),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("resolved_at", String, nullable=True),
    Column("prune_after", String, nullable=True),
    Column("provenance", String, nullable=False),
    CheckConstraint("sequence >= 1", name="calendar_write_sequence_positive"),
    CheckConstraint(
        "operation IN ('create', 'patch', 'cancel_occurrence', "
        "'delete_event', 'delete_series')",
        name="calendar_write_operation_valid",
    ),
    CheckConstraint(
        "recurrence_scope IN ('single', 'occurrence', 'series')",
        name="calendar_write_recurrence_scope_valid",
    ),
    CheckConstraint(
        "length(changed_fields_json) BETWEEN 2 AND 4096",
        name="calendar_write_field_mask_bounded",
    ),
    CheckConstraint(
        "base_values_json IS NULL OR length(base_values_json) <= 524288",
        name="calendar_write_base_values_bounded",
    ),
    CheckConstraint(
        "desired_values_json IS NULL OR length(desired_values_json) <= 524288",
        name="calendar_write_desired_values_bounded",
    ),
    CheckConstraint(
        "source_block_revision >= 1", name="calendar_write_revision_positive"
    ),
    CheckConstraint("schema_version = 1", name="calendar_write_schema_version_valid"),
    CheckConstraint(
        "state IN ('queued', 'ready', 'attempting', 'retry_wait', "
        "'reauth_required', 'conflict', 'ambiguous', 'failed', "
        "'completed', 'cancelled')",
        name="calendar_write_state_valid",
    ),
    CheckConstraint(
        "attempt_count BETWEEN 0 AND 5", name="calendar_write_attempt_count_bounded"
    ),
    CheckConstraint(
        "state <> 'retry_wait' OR next_attempt_at IS NOT NULL",
        name="calendar_write_retry_timestamp_required",
    ),
    CheckConstraint(
        "failure_class IS NULL OR failure_class IN "
        "('success', 'retryable_transport', 'retryable_backend', "
        "'retryable_quota', 'reauthentication_required', "
        "'stale_precondition', 'duplicate_or_ambiguous_create', "
        "'provider_not_found', 'invalid_target', "
        "'terminal_provider_rejection')",
        name="calendar_write_failure_class_valid",
    ),
    CheckConstraint(
        "failure_reason IS NULL OR length(failure_reason) <= 128",
        name="calendar_write_failure_reason_bounded",
    ),
    CheckConstraint(
        "provenance = 'direct_human'", name="calendar_write_provenance_valid"
    ),
    UniqueConstraint(
        "calendar_block_id", "sequence", name="uq_calendar_write_block_sequence"
    ),
)

calendar_provider_write_audit = Table(
    "calendar_provider_write_audit",
    metadata,
    Column("id", String(36), primary_key=True),
    Column("intent_id", String(36), nullable=False, index=True),
    Column("calendar_block_id", String(36), nullable=False, index=True),
    Column("action", String, nullable=False),
    Column("operation", String, nullable=False),
    Column("changed_fields_json", Text, nullable=False),
    Column("attempt_count", Integer, nullable=False),
    Column("safe_reason_class", String, nullable=True),
    Column("safe_reason", String, nullable=True),
    Column("from_state", String, nullable=True),
    Column("to_state", String, nullable=False),
    Column("source_revision", Integer, nullable=True),
    Column("resulting_revision", Integer, nullable=True),
    Column("occurred_at", String, nullable=False),
    Column("executor_provenance", String, nullable=False),
    CheckConstraint(
        "action IN ('write_intent_queued', 'write_intent_ready', "
        "'write_attempt_started', 'write_retry_scheduled', "
        "'write_reauthentication_required', 'write_outcome_ambiguous', "
        "'write_conflict_detected', 'write_failed_terminally', "
        "'write_completed', 'write_cancelled')",
        name="calendar_write_audit_action_valid",
    ),
    CheckConstraint(
        "operation IN ('create', 'patch', 'cancel_occurrence', "
        "'delete_event', 'delete_series')",
        name="calendar_write_audit_operation_valid",
    ),
    CheckConstraint(
        "(from_state IS NULL OR from_state IN "
        "('queued', 'ready', 'attempting', 'retry_wait', "
        "'reauth_required', 'conflict', 'ambiguous', 'failed', "
        "'completed', 'cancelled')) AND to_state IN "
        "('queued', 'ready', 'attempting', 'retry_wait', "
        "'reauth_required', 'conflict', 'ambiguous', 'failed', "
        "'completed', 'cancelled')",
        name="calendar_write_audit_state_valid",
    ),
    CheckConstraint(
        "length(changed_fields_json) BETWEEN 2 AND 4096",
        name="calendar_write_audit_fields_bounded",
    ),
    CheckConstraint(
        "attempt_count BETWEEN 0 AND 5",
        name="calendar_write_audit_attempt_bounded",
    ),
    CheckConstraint(
        "safe_reason IS NULL OR length(safe_reason) <= 128",
        name="calendar_write_audit_reason_bounded",
    ),
    CheckConstraint(
        "safe_reason_class IS NULL OR safe_reason_class IN "
        "('success', 'retryable_transport', 'retryable_backend', "
        "'retryable_quota', 'reauthentication_required', "
        "'stale_precondition', 'duplicate_or_ambiguous_create', "
        "'provider_not_found', 'invalid_target', "
        "'terminal_provider_rejection')",
        name="calendar_write_audit_reason_class_valid",
    ),
    CheckConstraint(
        "executor_provenance IN ('direct_human', 'recovery')",
        name="calendar_write_audit_provenance_valid",
    ),
)
