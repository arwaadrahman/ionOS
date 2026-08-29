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
    Column("last_auth_at", String, nullable=True),
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("revision", Integer, nullable=False, server_default="1"),
    CheckConstraint(
        "auth_state IN ('connected', 'reauth_required', 'disconnected')",
        name="google_account_auth_state_valid",
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
    Column("created_at", String, nullable=False),
    Column("updated_at", String, nullable=False),
    Column("revision", Integer, nullable=False, server_default="1"),
    CheckConstraint(
        "flexibility IN ('locked', 'flexible', 'ion_controlled')",
        name="calendar_block_flexibility_valid",
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
    Column("last_seen_sync_generation", String(36), nullable=False),
    CheckConstraint(
        "(original_start_kind = 'none' AND original_start_date IS NULL "
        "AND original_start_at IS NULL AND original_start_timezone IS NULL) OR "
        "(original_start_kind = 'date' AND original_start_date IS NOT NULL "
        "AND original_start_at IS NULL AND original_start_timezone IS NULL) OR "
        "(original_start_kind = 'instant' AND original_start_date IS NULL "
        "AND original_start_at IS NOT NULL AND original_start_timezone IS NOT NULL)",
        name="google_event_original_start_union_valid",
    ),
    UniqueConstraint(
        "calendar_id", "provider_event_id", name="uq_google_event_calendar_event_id"
    ),
)
