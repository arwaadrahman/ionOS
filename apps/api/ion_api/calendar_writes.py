"""Durable, provider-free Phase 2C-1 Calendar write foundation."""

from __future__ import annotations

import base64
import hashlib
import json
import math
import secrets
from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from sqlalchemy import Engine, delete, func, insert, select, update

from ion_api.calendar import (
    CalendarConflictError,
    CalendarNotFoundError,
    CalendarService,
    CalendarValidationError,
)
from ion_api.calendar_contracts import ProviderDateTime
from ion_api.calendar_write_contracts import (
    AccountWriteCapabilityOutput,
    ApplyIonChangesInput,
    BeginWriteAttemptInput,
    BlockWriteCapabilityOutput,
    CalendarWriteCapabilityOutput,
    CalendarWriteFoundationOutput,
    CreateProviderEventInput,
    DeleteProviderEventInput,
    EditProviderEventInput,
    KeepGoogleVersionInput,
    ProviderRecurrenceIdentity,
    ProviderWriteIntentSummaryOutput,
    ProviderWritePlanOutput,
    ProviderWriteValues,
    PruneResultOutput,
    PruneWriteIntentsInput,
    QueueProviderWriteIntentInput,
    ReadyWriteIntentsInput,
    ReconcileProviderCreateInput,
    ReconcileProviderDeleteInput,
    ReconcileProviderPatchInput,
    RecordProviderWriteResultInput,
    RecoverWriteIntentsInput,
    RecoveryResultOutput,
    RecurrencePreset,
    ResolveProviderOccurrenceInput,
    ReviewDifferencesOutput,
    WriteIntentTransitionInput,
)
from ion_api.schema import (
    audit_events,
    calendar_block_ion_metadata,
    calendar_blocks,
    calendar_provider_write_audit,
    calendar_provider_write_intents,
    google_accounts,
    google_calendars,
    google_event_links,
)

EVENT_ID_DOMAIN = b"ion:google-calendar:event-id:v1\0"
COMPLETED_RETENTION_DAYS = 30
MAX_AUTOMATIC_ATTEMPTS = 5
MAX_BACKOFF_SECONDS = 300
UNTITLED_EVENT = "Untitled event"
RECURRENCE_PRESET_RULES: dict[RecurrencePreset, list[str]] = {
    "none": [],
    "daily": ["RRULE:FREQ=DAILY"],
    "weekdays": ["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"],
    "weekly": ["RRULE:FREQ=WEEKLY"],
    "monthly": ["RRULE:FREQ=MONTHLY"],
    "yearly": ["RRULE:FREQ=YEARLY"],
}
TERMINAL_PREDECESSOR_STATES = ("completed", "cancelled")
# States a human resolution action may act on. `conflict` is ADR 0021's
# explicit conflict exit. `failed` uses the same accepted vocabulary: the
# pending provider-field intent is discarded (Keep Google) or re-authorized
# against fresh confirmed authority as a new retry generation (Apply my Ion
# changes). Without this, a terminally failed write left its CalendarBlock
# permanently uneditable, because a failed predecessor keeps serializing the
# block and `failed -> cancelled` had no human entry point.
RESOLVABLE_INTENT_STATES = ("conflict", "failed")
# Conflict reasons the superseded policy produced for *ordinary* version drift.
# Under the accepted contract that is sync concurrency, not a semantic conflict,
# so a row carrying one of these is re-armed automatically instead of trapping
# the owner in a workflow the product no longer has.
LEGACY_ORDINARY_DRIFT_REASONS = (
    "provider_etag_changed",
    "provider_etag_changed_during_refresh",
    "provider_values_changed",
    "recurrence_master_changed",
)
# Ordinary ETag drift is no longer a human decision. A patch whose precondition
# went stale re-reads confirmed provider state and retries its own narrow field
# mask against the fresh ETag, bounded by MAX_AUTOMATIC_ATTEMPTS. `conflict` is
# now reserved for contradictions a rebase cannot honestly resolve -- the
# provider target changed identity, was deleted, or became unsupported.
# Supersedes the original ADR 0021 rule that every mismatch required review.
NONTERMINAL_INTENT_STATES = (
    "queued",
    "ready",
    "attempting",
    "retry_wait",
    "reauth_required",
    "ambiguous",
)
ALLOWED_TRANSITIONS = {
    "queued": frozenset(("ready", "cancelled")),
    "ready": frozenset(("attempting", "cancelled")),
    "attempting": frozenset(
        (
            "completed",
            "retry_wait",
            "reauth_required",
            "conflict",
            "ambiguous",
            "failed",
        )
    ),
    "retry_wait": frozenset(("ready", "cancelled")),
    "reauth_required": frozenset(("ready", "cancelled")),
    # `ambiguous -> ready` is the automatic rebase: confirmed provider state has
    # just been re-read, so the same intent re-arms against the fresh ETag.
    "ambiguous": frozenset(("attempting", "ready", "conflict", "failed", "cancelled")),
    # `conflict -> ready` re-arms a row the superseded policy conflicted for
    # ordinary drift; see LEGACY_ORDINARY_DRIFT_REASONS.
    "conflict": frozenset(("ready", "cancelled")),
    # `failed -> ready` re-arms an intent whose failure described a provider
    # target that has since moved; recovery retries rather than escalating.
    "failed": frozenset(("ready", "cancelled")),
    "completed": frozenset(),
    "cancelled": frozenset(),
}


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_timestamp(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as error:
        raise CalendarValidationError("invalid timestamp") from error
    if parsed.tzinfo is None:
        raise CalendarValidationError("timestamp must include an offset")
    return parsed.astimezone(UTC)


def _seconds_until(target: str | None, now: str) -> int | None:
    """Whole seconds from `now` until `target`, never negative, or None.

    Reported as a delay rather than an instant so the dispatcher can schedule
    its own wake without needing a clock or a date parser of its own.
    """
    if target is None:
        return None
    remaining = (_parse_timestamp(target) - _parse_timestamp(now)).total_seconds()
    return max(0, math.ceil(remaining))


def _canonical_timestamp(value: str) -> str:
    return (
        _parse_timestamp(value)
        .isoformat(timespec="microseconds")
        .replace("+00:00", "Z")
    )


def deterministic_google_event_id(calendar_block_id: str) -> str:
    try:
        block_uuid = UUID(calendar_block_id)
    except ValueError as error:
        raise CalendarValidationError("CalendarBlock ID must be a UUID") from error
    digest = hashlib.sha256(EVENT_ID_DOMAIN + block_uuid.bytes).digest()[:20]
    return base64.b32hexencode(digest).decode("ascii").lower()


def full_jitter_delay_seconds(attempt_count: int, random_fraction: float) -> int:
    if not 1 <= attempt_count <= MAX_AUTOMATIC_ATTEMPTS:
        raise CalendarValidationError("attempt count is outside the retry policy")
    if not 0 <= random_fraction < 1:
        raise CalendarValidationError("jitter source must be in [0, 1)")
    ceiling = min(30 * 2 ** (attempt_count - 1), MAX_BACKOFF_SECONDS)
    return math.floor(ceiling * random_fraction)


def _validated_zone(value: str) -> ZoneInfo:
    try:
        return ZoneInfo(value)
    except ZoneInfoNotFoundError as error:
        raise CalendarValidationError(
            "timed create requires an IANA timezone"
        ) from error


def _resolved_wall_time(date_value: str, time_value: str, timezone: str) -> datetime:
    civil = datetime.combine(
        date.fromisoformat(date_value), time.fromisoformat(time_value)
    )
    zone = _validated_zone(timezone)
    candidates: list[datetime] = []
    for fold in (0, 1):
        aware = civil.replace(tzinfo=zone, fold=fold)
        round_trip = aware.astimezone(UTC).astimezone(zone)
        if round_trip.replace(tzinfo=None) == civil and round_trip.fold == fold:
            candidates.append(aware)
    if not candidates:
        raise CalendarValidationError("timed create falls in a skipped DST interval")
    if len(candidates) == 2 and candidates[0].utcoffset() != candidates[1].utcoffset():
        raise CalendarValidationError("timed create is ambiguous across a DST fold")
    return candidates[0]


def _create_temporal_values(
    input: CreateProviderEventInput,
) -> tuple[dict[str, str | None], dict[str, object]]:
    if input.all_day:
        start_date = date.fromisoformat(input.date)
        end_date = start_date + timedelta(days=1)
        return (
            {
                "temporal_kind": "all_day",
                "start_date": start_date.isoformat(),
                "end_date": end_date.isoformat(),
                "start_at": None,
                "end_at": None,
                "start_timezone": None,
                "end_timezone": None,
            },
            {
                "start": {"date": start_date.isoformat()},
                "end": {"date": end_date.isoformat()},
            },
        )
    start = _resolved_wall_time(input.date, input.start_time, input.timezone)
    end = _resolved_wall_time(input.date, input.end_time, input.timezone)
    if end <= start:
        raise CalendarValidationError("timed create end must be after start")
    start_at = start.isoformat(timespec="seconds")
    end_at = end.isoformat(timespec="seconds")
    return (
        {
            "temporal_kind": "timed",
            "start_date": None,
            "end_date": None,
            "start_at": start_at,
            "end_at": end_at,
            "start_timezone": input.timezone,
            "end_timezone": input.timezone,
        },
        {
            "start": {"date_time": start_at, "timezone": input.timezone},
            "end": {"date_time": end_at, "timezone": input.timezone},
        },
    )


def bounded_recurrence_rules(preset: RecurrencePreset) -> list[str]:
    return list(RECURRENCE_PRESET_RULES[preset])


def bounded_recurrence_preset(rules: list[str]) -> RecurrencePreset | None:
    for preset, expected in RECURRENCE_PRESET_RULES.items():
        if rules == expected:
            return preset
    return None


def terminated_recurrence_rules(preset: RecurrencePreset, until: str) -> list[str]:
    """Bounded `this and following` termination for an already-supported
    preset. The owner-authorized recurrence contract permits exactly the five
    preset families plus a domain-generated UNTIL; the renderer can never
    supply recurrence text, a FREQ, a BY* clause, or a termination value."""
    base = RECURRENCE_PRESET_RULES[preset]
    if not base:
        raise CalendarValidationError("recurrence_unsupported")
    if not _valid_recurrence_until(until):
        raise CalendarValidationError("recurrence_identity_unresolved")
    return [f"{base[0]};UNTIL={until}"]


def _valid_recurrence_until(value: str) -> bool:
    """`YYYYMMDD` for an all-day series, or basic UTC `YYYYMMDDTHHMMSSZ` for a
    timed one. RFC 5545 requires a timed UNTIL to be UTC when DTSTART carries a
    timezone, which is exactly how Google stores these series."""
    if len(value) == 8:
        return value.isdigit() and _valid_civil_date(value)
    if len(value) == 16 and value[8] == "T" and value[15] == "Z":
        return (
            value[:8].isdigit()
            and value[9:15].isdigit()
            and _valid_civil_date(value[:8])
            and int(value[9:11]) < 24
            and int(value[11:13]) < 60
            and int(value[13:15]) < 60
        )
    return False


def _valid_civil_date(value: str) -> bool:
    try:
        date(int(value[:4]), int(value[4:6]), int(value[6:8]))
    except ValueError:
        return False
    return True


def series_trim_until(block, original_start: ProviderDateTime) -> str:
    """Terminate the old master immediately before the selected occurrence.

    Derived only from trusted state: the block's persisted temporal kind and
    IANA timezone, plus the selected occurrence's immutable original start.
    All-day series terminate on the previous civil date, so no midnight instant
    is ever fabricated. Timed series terminate one second before the selected
    instant in UTC, which is DST-safe because it is computed on the absolute
    instant rather than on wall-clock arithmetic.
    """
    if block.temporal_kind == "all_day":
        if not original_start.date:
            raise CalendarValidationError("recurrence_identity_unresolved")
        previous = date.fromisoformat(original_start.date) - timedelta(days=1)
        return previous.strftime("%Y%m%d")
    if not original_start.date_time:
        raise CalendarValidationError("recurrence_identity_unresolved")
    instant = _parse_timestamp(original_start.date_time).astimezone(UTC)
    return (instant - timedelta(seconds=1)).strftime("%Y%m%dT%H%M%SZ")


def _json(value) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"))


def _values_json(value) -> str | None:
    if value is None:
        return None
    return _json(value.model_dump(mode="json", exclude_none=True))


def _calendar_reason(account, calendar) -> str:
    if (
        account.auth_state != "connected"
        or account.calendar_write_scope_state == "reauth_required"
    ):
        return "reauth_required"
    if account.calendar_write_scope_state != "write_granted":
        return "account_read_only"
    if calendar.provider_deleted:
        return "calendar_deleted"
    if not calendar.enabled_in_ion:
        return "calendar_disabled"
    if calendar.access_role not in ("writer", "owner"):
        return "access_role_read_only"
    return "eligible"


def _write_reason(
    account,
    calendar,
    link=None,
    block=None,
    *,
    allow_pending_create=False,
    allow_recurrence=False,
) -> str:
    calendar_reason = _calendar_reason(account, calendar)
    if calendar_reason != "eligible":
        return calendar_reason
    if link is None:
        return "provider_unconfirmed"
    if link.provider_event_type != "default":
        return "special_event"
    if bool(link.provider_locked):
        return "provider_locked"
    if bool(link.has_attendees):
        return "attendees_present"
    if block is not None and (
        block.status == "cancelled" or block.provider_deleted_at is not None
    ):
        return "provider_deleted"
    if link.link_state != "confirmed" and not (
        allow_pending_create and link.link_state == "pending_create"
    ):
        return "provider_unconfirmed"
    if link.link_state == "confirmed" and (
        not link.provider_etag or link.provider_etag == "*"
    ):
        return "provider_unconfirmed"
    if block is not None and block.recurrence_kind != "single" and not allow_recurrence:
        return "recurrence_unsupported"
    return "eligible"


def _summary(row) -> ProviderWriteIntentSummaryOutput:
    return ProviderWriteIntentSummaryOutput(
        id=row.id,
        calendar_block_id=row.calendar_block_id,
        operation=row.operation,
        recurrence_scope=row.recurrence_scope,
        changed_fields=json.loads(row.changed_fields_json),
        state=row.state,
        attempt_count=row.attempt_count,
        next_attempt_at=row.next_attempt_at,
        failure_class=row.failure_class,
        failure_reason=row.failure_reason,
        created_at=row.created_at,
        updated_at=row.updated_at,
        resolved_at=row.resolved_at,
        provenance=row.provenance,
    )


def _plan(row) -> ProviderWritePlanOutput:
    return ProviderWritePlanOutput(
        **_summary(row).model_dump(),
        account_id=row.account_id,
        calendar_id=row.calendar_id,
        provider_event_id=row.provider_event_id,
        expected_provider_etag=row.expected_provider_etag,
        base_values=json.loads(row.base_values_json) if row.base_values_json else None,
        desired_values=(
            json.loads(row.desired_values_json) if row.desired_values_json else None
        ),
        source_block_revision=row.source_block_revision,
        schema_version=row.schema_version,
    )


def _audit(
    connection,
    row,
    *,
    action: str,
    from_state: str | None,
    to_state: str,
    occurred_at: str,
    executor_provenance: str,
    resulting_revision: int | None = None,
) -> None:
    connection.execute(
        insert(calendar_provider_write_audit).values(
            id=str(uuid4()),
            intent_id=row.id,
            calendar_block_id=row.calendar_block_id,
            action=action,
            operation=row.operation,
            changed_fields_json=row.changed_fields_json,
            attempt_count=row.attempt_count,
            safe_reason_class=row.failure_class,
            safe_reason=row.failure_reason,
            from_state=from_state,
            to_state=to_state,
            source_revision=row.source_block_revision,
            resulting_revision=resulting_revision,
            occurred_at=occurred_at,
            executor_provenance=executor_provenance,
        )
    )


def _canonical_audit(
    connection,
    *,
    block_id: str,
    action: str,
    command_id: str,
    from_revision: int | None,
    to_revision: int | None,
) -> None:
    human_requested = action.endswith("_requested")
    connection.execute(
        insert(audit_events).values(
            event_id=str(uuid4()),
            occurred_at=utc_now(),
            entity_type="calendar_block",
            entity_id=block_id,
            action=action,
            actor_kind="human" if human_requested else "integration",
            authority="direct" if human_requested else "approved",
            source="desktop" if human_requested else "google_calendar",
            from_revision=from_revision,
            to_revision=to_revision,
            command_id=command_id,
        )
    )


def _event_temporal_values(event) -> dict[str, str | None]:
    if event.start.date is not None:
        return {
            "temporal_kind": "all_day",
            "start_date": event.start.date,
            "end_date": event.end.date,
            "start_at": None,
            "end_at": None,
            "start_timezone": None,
            "end_timezone": None,
        }
    return {
        "temporal_kind": "timed",
        "start_date": None,
        "end_date": None,
        "start_at": event.start.date_time,
        "end_at": event.end.date_time,
        "start_timezone": event.start.timezone,
        "end_timezone": event.end.timezone,
    }


def _block_temporal_contract(block) -> dict[str, object]:
    if block.temporal_kind == "all_day":
        return {
            "start": {"date": block.start_date},
            "end": {"date": block.end_date},
        }
    return {
        "start": {
            "date_time": block.start_at,
            "timezone": block.start_timezone,
        },
        "end": {
            "date_time": block.end_at,
            "timezone": block.end_timezone,
        },
    }


def _event_matches_changed_values(row, event) -> bool:
    desired = json.loads(row.desired_values_json)
    changed = set(json.loads(row.changed_fields_json))
    if "title" in changed and (event.title or UNTITLED_EVENT) != desired.get("title"):
        return False
    if "temporal" in changed:
        expected_start = ProviderDateTime.model_validate(desired.get("start"))
        expected_end = ProviderDateTime.model_validate(desired.get("end"))
        if not event.start or not event.end:
            return False
        if not _same_provider_time(event.start, expected_start):
            return False
        if not _same_provider_time(event.end, expected_end):
            return False
    if "recurrence" in changed and event.recurrence != desired.get("recurrence"):
        return False
    if "status" in changed and event.status != desired.get("status"):
        return False
    return True


def _same_provider_time(left, right) -> bool:
    if left.date is not None or right.date is not None:
        return left.date == right.date and left.timezone == right.timezone
    left_at = _parse_timestamp(left.date_time)
    right_at = _parse_timestamp(right.date_time)
    return left_at == right_at and left.timezone == right.timezone


def _identity_lookup_matches(row, event) -> bool:
    desired = json.loads(row.desired_values_json)
    if event.title != desired.get("title"):
        return False
    if event.transparency != desired.get("transparency", "opaque"):
        return False
    expected_start = desired.get("start")
    expected_end = desired.get("end")
    if expected_start is None or expected_end is None:
        return False
    matches = _same_provider_time(
        event.start, ProviderDateTime.model_validate(expected_start)
    ) and _same_provider_time(event.end, ProviderDateTime.model_validate(expected_end))
    if not matches:
        return False
    expected_recurrence = desired.get("recurrence")
    return expected_recurrence is None or event.recurrence == expected_recurrence


def _block_start_provider_time(block) -> ProviderDateTime:
    if block.temporal_kind == "all_day":
        return ProviderDateTime(date=block.start_date)
    return ProviderDateTime(date_time=block.start_at, timezone=block.start_timezone)


def _provider_time_from_link(link) -> ProviderDateTime:
    if link.original_start_kind == "date":
        return ProviderDateTime(date=link.original_start_date)
    if link.original_start_kind == "instant":
        return ProviderDateTime(
            date_time=link.original_start_at,
            timezone=link.original_start_timezone,
        )
    raise CalendarValidationError("recurrence exception lacks original-start identity")


def _same_original_start(left, right) -> bool:
    return _same_provider_time(left, right)


def _predecessor_targets_same_occurrence(
    predecessor, occurrence_original_start
) -> bool:
    if (
        predecessor.recurrence_scope != "occurrence"
        or occurrence_original_start is None
    ):
        return False
    base = ProviderWriteValues.model_validate_json(predecessor.base_values_json)
    identity = base.recurrence_identity
    if identity is None or identity.original_start is None:
        return False
    return _same_original_start(identity.original_start, occurrence_original_start)


def _predecessor_blocks_new_write(
    predecessor, recurrence_scope: str, occurrence_original_start
) -> bool:
    """A master serializes writes only while a predecessor is genuinely
    in flight, or while it directly concerns the exact same recurrence
    target as the new write. A resolved (conflict/failed) predecessor on a
    *different* occurrence must not keep serializing the rest of the master.
    """
    if predecessor.state in TERMINAL_PREDECESSOR_STATES:
        return False
    if predecessor.state in NONTERMINAL_INTENT_STATES:
        return True
    # predecessor.state is a terminal but reviewable outcome: "conflict" or
    # "failed". It still blocks a write that directly targets the master
    # (series/single scope, or a non-occurrence predecessor) and blocks
    # retrying the exact occurrence it concerns, but must release any other,
    # unrelated occurrence of the same master.
    if predecessor.recurrence_scope != "occurrence" or recurrence_scope != "occurrence":
        return True
    return _predecessor_targets_same_occurrence(predecessor, occurrence_original_start)


def _occurrence_temporal_contract(master, original_start) -> dict[str, object]:
    if master.temporal_kind == "all_day":
        start = date.fromisoformat(original_start.date)
        duration = date.fromisoformat(master.end_date) - date.fromisoformat(
            master.start_date
        )
        return {
            "start": {"date": start.isoformat()},
            "end": {"date": (start + duration).isoformat()},
        }
    original = _parse_timestamp(original_start.date_time)
    duration = _parse_timestamp(master.end_at) - _parse_timestamp(master.start_at)
    zone = _validated_zone(master.start_timezone)
    start = original.astimezone(zone)
    end = (original + duration).astimezone(zone)
    return {
        "start": {
            "date_time": start.isoformat(timespec="seconds"),
            "timezone": master.start_timezone,
        },
        "end": {
            "date_time": end.isoformat(timespec="seconds"),
            "timezone": master.end_timezone,
        },
    }


class CalendarWriteService:
    def __init__(self, engine: Engine, random_fraction=None):
        self.engine = engine
        self.random_fraction = random_fraction or (
            lambda: secrets.randbelow(1_000_000) / 1_000_000
        )

    @staticmethod
    def _required_row(connection, table, identifier: str, column=None):
        key = column if column is not None else table.c.id
        row = connection.execute(select(table).where(key == identifier)).one_or_none()
        if row is None:
            raise CalendarNotFoundError(identifier)
        return row

    def _recurrence_target(
        self, connection, selected_block, recurrence_scope: str, original_start
    ):
        selected_link = self._required_row(
            connection,
            google_event_links,
            selected_block.id,
            google_event_links.c.calendar_block_id,
        )
        if recurrence_scope == "single":
            if selected_block.recurrence_kind != "single" or original_start is not None:
                raise CalendarValidationError("single scope requires a single event")
            return selected_block, selected_link, None
        if selected_block.recurrence_kind == "master":
            master = selected_block
            master_link = selected_link
            exception_block_id = None
        elif selected_block.recurrence_kind == "exception":
            if not selected_block.recurrence_master_block_id:
                raise CalendarValidationError("recurrence_identity_unresolved")
            master = self._required_row(
                connection, calendar_blocks, selected_block.recurrence_master_block_id
            )
            master_link = self._required_row(
                connection,
                google_event_links,
                master.id,
                google_event_links.c.calendar_block_id,
            )
            exception_block_id = selected_block.id
        else:
            raise CalendarValidationError("recurrence scope requires a recurring event")
        if master.recurrence_kind != "master" or not master_link.provider_etag:
            raise CalendarValidationError("recurrence_identity_unresolved")
        if recurrence_scope == "series":
            if original_start is not None:
                raise CalendarValidationError(
                    "series scope targets the canonical master"
                )
            return master, master_link, exception_block_id
        if original_start is None:
            raise CalendarValidationError(
                "occurrence scope requires original-start identity"
            )
        if selected_block.recurrence_kind == "exception" and not _same_original_start(
            _provider_time_from_link(selected_link), original_start
        ):
            raise CalendarConflictError(selected_block.id)
        return master, master_link, exception_block_id

    def foundation(self, limit: int = 100) -> CalendarWriteFoundationOutput:
        bounded_limit = max(1, min(limit, 100))
        with self.engine.connect() as connection:
            accounts = connection.execute(
                select(google_accounts).order_by(google_accounts.c.created_at)
            ).all()
            calendars = connection.execute(
                select(google_calendars).order_by(google_calendars.c.created_at)
            ).all()
            account_by_id = {row.id: row for row in accounts}
            links = connection.execute(
                select(google_event_links).order_by(
                    google_event_links.c.calendar_block_id
                )
            ).all()
            blocks = connection.execute(select(calendar_blocks)).all()
            block_by_id = {row.id: row for row in blocks}
            calendar_by_id = {row.id: row for row in calendars}
            pending_rows = connection.execute(
                select(calendar_provider_write_intents)
                .where(
                    calendar_provider_write_intents.c.state.not_in(
                        TERMINAL_PREDECESSOR_STATES
                    )
                )
                .order_by(calendar_provider_write_intents.c.created_at)
                .limit(bounded_limit)
            ).all()
        pending_block_ids = {row.calendar_block_id for row in pending_rows}

        def block_reason(link) -> str:
            block = block_by_id[link.calendar_block_id]
            reason = _write_reason(
                account_by_id[link.account_id],
                calendar_by_id[link.calendar_id],
                link,
                block,
                allow_recurrence=(block.recurrence_kind != "single"),
            )
            serialization_block_id = (
                block.recurrence_master_block_id
                if block.recurrence_kind == "exception"
                else block.id
            )
            if reason == "eligible" and serialization_block_id in pending_block_ids:
                return "write_pending"
            return reason

        return CalendarWriteFoundationOutput(
            accounts=[
                AccountWriteCapabilityOutput(
                    account_id=row.id,
                    state=row.calendar_write_scope_state,
                    write_capable=(
                        row.auth_state == "connected"
                        and row.calendar_write_scope_state == "write_granted"
                    ),
                )
                for row in accounts
            ],
            calendars=[
                CalendarWriteCapabilityOutput(
                    calendar_id=row.id,
                    eligible=(
                        _calendar_reason(account_by_id[row.account_id], row)
                        == "eligible"
                    ),
                    reason=_calendar_reason(account_by_id[row.account_id], row),
                )
                for row in calendars
            ],
            blocks=[
                BlockWriteCapabilityOutput(
                    calendar_block_id=link.calendar_block_id,
                    eligible=block_reason(link) == "eligible",
                    reason=block_reason(link),
                )
                for link in links
            ],
            pending=[_summary(row) for row in pending_rows],
        )

    def create(
        self, input: CreateProviderEventInput
    ) -> ProviderWriteIntentSummaryOutput:
        title = input.title.strip()
        if not title:
            raise CalendarValidationError("create title must be present")
        temporal, provider_temporal = _create_temporal_values(input)
        recurrence = bounded_recurrence_rules(input.recurrence)
        now = utc_now()
        with self.engine.begin() as connection:
            existing = connection.execute(
                select(calendar_provider_write_intents).where(
                    calendar_provider_write_intents.c.command_id == input.command_id
                )
            ).one_or_none()
            if existing is not None:
                if existing.operation != "create":
                    raise CalendarConflictError(input.command_id)
                return _summary(existing)

            calendar = self._required_row(
                connection, google_calendars, input.calendar_id
            )
            account = self._required_row(
                connection, google_accounts, calendar.account_id
            )
            reason = _calendar_reason(account, calendar)
            if reason != "eligible":
                raise CalendarValidationError(reason)

            block_id = str(uuid4())
            intent_id = str(uuid4())
            provider_event_id = deterministic_google_event_id(block_id)
            changed_fields = ["title", "transparency", "temporal"]
            if recurrence:
                changed_fields.append("recurrence")
            changed_fields_json = _json(changed_fields)
            desired_values_json = _json(
                {
                    "schema_version": 1,
                    "title": title,
                    "transparency": "opaque",
                    **provider_temporal,
                    **({"recurrence": recurrence} if recurrence else {}),
                }
            )
            connection.execute(
                insert(calendar_blocks).values(
                    id=block_id,
                    source_kind="google",
                    title=title,
                    description=None,
                    location=None,
                    status="confirmed",
                    transparency="opaque",
                    recurrence_kind="master" if recurrence else "single",
                    recurrence_rules=_json(recurrence) if recurrence else None,
                    recurrence_master_block_id=None,
                    provider_deleted_at=None,
                    created_at=now,
                    updated_at=now,
                    revision=1,
                    trashed_at=None,
                    **temporal,
                )
            )
            connection.execute(
                insert(calendar_block_ion_metadata).values(
                    calendar_block_id=block_id,
                    flexibility="locked",
                    notes=None,
                    category=None,
                    category_subtype=None,
                    created_at=now,
                    updated_at=now,
                    revision=1,
                )
            )
            connection.execute(
                insert(google_event_links).values(
                    calendar_block_id=block_id,
                    account_id=account.id,
                    calendar_id=calendar.id,
                    provider_event_id=provider_event_id,
                    ical_uid=None,
                    provider_etag=None,
                    provider_updated_at=None,
                    recurring_event_id=None,
                    original_start_kind="none",
                    original_start_date=None,
                    original_start_at=None,
                    original_start_timezone=None,
                    last_seen_sync_generation=None,
                    link_state="pending_create",
                    provider_event_type="default",
                    provider_locked=False,
                    has_attendees=False,
                )
            )
            connection.execute(
                insert(calendar_provider_write_intents).values(
                    id=intent_id,
                    command_id=input.command_id,
                    calendar_block_id=block_id,
                    account_id=account.id,
                    calendar_id=calendar.id,
                    provider_event_id=provider_event_id,
                    sequence=1,
                    predecessor_intent_id=None,
                    operation="create",
                    recurrence_scope="series" if recurrence else "single",
                    changed_fields_json=changed_fields_json,
                    base_values_json=None,
                    desired_values_json=desired_values_json,
                    expected_provider_etag=None,
                    source_block_revision=1,
                    schema_version=1,
                    state="queued",
                    attempt_count=0,
                    next_attempt_at=None,
                    last_attempt_at=None,
                    failure_class=None,
                    failure_reason=None,
                    created_at=now,
                    updated_at=now,
                    resolved_at=None,
                    prune_after=None,
                    provenance=input.provenance,
                )
            )
            queued = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            _canonical_audit(
                connection,
                block_id=block_id,
                action="create_requested",
                command_id=input.command_id,
                from_revision=None,
                to_revision=1,
            )
            _audit(
                connection,
                queued,
                action="write_intent_queued",
                from_state=None,
                to_state="queued",
                occurred_at=now,
                executor_provenance="direct_human",
            )
            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == intent_id)
                .values(state="ready", updated_at=now)
            )
            ready = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            _audit(
                connection,
                ready,
                action="write_intent_ready",
                from_state="queued",
                to_state="ready",
                occurred_at=now,
                executor_provenance="direct_human",
            )
            return _summary(ready)

    def edit(self, input: EditProviderEventInput) -> ProviderWriteIntentSummaryOutput:
        now = utc_now()
        with self.engine.begin() as connection:
            existing_command = connection.execute(
                select(calendar_provider_write_intents).where(
                    calendar_provider_write_intents.c.command_id == input.command_id
                )
            ).one_or_none()
            if existing_command is not None:
                if existing_command.operation != "patch":
                    raise CalendarConflictError(input.command_id)
                return _summary(existing_command)

            selected_block = self._required_row(
                connection, calendar_blocks, input.calendar_block_id
            )
            if selected_block.revision != input.expected_block_revision:
                raise CalendarConflictError(input.calendar_block_id)
            if input.recurrence_scope == "this_and_following":
                return self._split_series(connection, selected_block, input, now)
            block, link, exception_block_id = self._recurrence_target(
                connection,
                selected_block,
                input.recurrence_scope,
                input.occurrence_original_start,
            )
            account = self._required_row(connection, google_accounts, link.account_id)
            calendar = self._required_row(
                connection, google_calendars, link.calendar_id
            )
            reason = _write_reason(
                account,
                calendar,
                link,
                block,
                allow_recurrence=input.recurrence_scope != "single",
            )
            if reason != "eligible":
                raise CalendarValidationError(reason)
            if selected_block.id != block.id:
                selected_link = self._required_row(
                    connection,
                    google_event_links,
                    selected_block.id,
                    google_event_links.c.calendar_block_id,
                )
                selected_reason = _write_reason(
                    account,
                    calendar,
                    selected_link,
                    selected_block,
                    allow_recurrence=True,
                )
                if selected_reason != "eligible":
                    raise CalendarValidationError(selected_reason)
            # An edit is reversible: it targets a confirmed ETag, leaves every
            # occurrence in place, and stays undoable. Ion therefore does not gate
            # ordinary edits behind a confirmation and keeps that stronger step for
            # operations that remove confirmed occurrences.

            latest = connection.execute(
                select(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.calendar_block_id == block.id)
                .order_by(calendar_provider_write_intents.c.sequence.desc())
                .limit(1)
            ).one_or_none()
            # A newer direct-human mutation is always accepted. One concerning
            # a different occurrence of the same master is independent; one
            # concerning the same target is superseded or queued behind, never
            # refused.
            predecessor_id: str | None = None
            initial_state = "ready"
            if latest is not None and _predecessor_blocks_new_write(
                latest, input.recurrence_scope, input.occurrence_original_start
            ):
                predecessor_id, initial_state = self._supersede_or_chain(
                    connection, latest, now
                )

            changed_fields: list[str] = []
            base: dict[str, object] = {"schema_version": 1}
            desired: dict[str, object] = {"schema_version": 1}
            value_block = selected_block if exception_block_id else block
            if input.recurrence_scope == "occurrence":
                base["recurrence_identity"] = ProviderRecurrenceIdentity(
                    master_provider_event_id=link.provider_event_id,
                    master_provider_etag=link.provider_etag,
                    original_start=input.occurrence_original_start,
                    exception_calendar_block_id=exception_block_id,
                ).model_dump(mode="json", exclude_none=True)
            if input.title is not None:
                title = input.title.strip()
                if not title:
                    raise CalendarValidationError("edit title must be present")
                if title != value_block.title:
                    changed_fields.append("title")
                    base["title"] = value_block.title
                    desired["title"] = title

            temporal_requested = (
                input.start_date is not None or input.end_date is not None
            )
            if (
                input.edit_kind in ("move", "resize")
                and value_block.temporal_kind != "timed"
            ):
                raise CalendarValidationError("timed operation requires a timed event")
            if temporal_requested:
                base_temporal = (
                    _occurrence_temporal_contract(
                        block, input.occurrence_original_start
                    )
                    if input.recurrence_scope == "occurrence"
                    and exception_block_id is None
                    else _block_temporal_contract(value_block)
                )
                if value_block.temporal_kind == "all_day":
                    if input.edit_kind != "edit" or any(
                        value is not None
                        for value in (input.start_time, input.end_time, input.timezone)
                    ):
                        raise CalendarValidationError(
                            "all-day conversion and direct manipulation are unsupported"
                        )
                    start_date = date.fromisoformat(input.start_date)
                    end_date = date.fromisoformat(input.end_date)
                    if end_date <= start_date:
                        raise CalendarValidationError(
                            "all-day end must be after start and remains end-exclusive"
                        )
                    desired_temporal = {
                        "start": {"date": start_date.isoformat()},
                        "end": {"date": end_date.isoformat()},
                    }
                else:
                    if (
                        not input.timezone
                        or input.timezone != value_block.start_timezone
                        or input.timezone != value_block.end_timezone
                    ):
                        raise CalendarValidationError("timezone_change_unsupported")
                    if input.edit_kind == "move":
                        start = _resolved_wall_time(
                            input.start_date, input.start_time, input.timezone
                        )
                        duration = _parse_timestamp(
                            base_temporal["end"]["date_time"]
                        ) - _parse_timestamp(base_temporal["start"]["date_time"])
                        end = (start.astimezone(UTC) + duration).astimezone(
                            _validated_zone(input.timezone)
                        )
                    elif input.edit_kind == "resize":
                        if input.start_date is not None:
                            start = _resolved_wall_time(
                                input.start_date, input.start_time, input.timezone
                            )
                            end = datetime.fromisoformat(
                                base_temporal["end"]["date_time"]
                            )
                        else:
                            start = datetime.fromisoformat(
                                base_temporal["start"]["date_time"]
                            )
                            end = _resolved_wall_time(
                                input.end_date, input.end_time, input.timezone
                            )
                    else:
                        start = _resolved_wall_time(
                            input.start_date, input.start_time, input.timezone
                        )
                        end = _resolved_wall_time(
                            input.end_date, input.end_time, input.timezone
                        )
                    if end <= start:
                        raise CalendarValidationError(
                            "timed edit end must be after start"
                        )
                    desired_temporal = {
                        "start": {
                            "date_time": start.isoformat(timespec="seconds"),
                            "timezone": input.timezone,
                        },
                        "end": {
                            "date_time": end.isoformat(timespec="seconds"),
                            "timezone": input.timezone,
                        },
                    }
                if desired_temporal != base_temporal:
                    changed_fields.append("temporal")
                    base.update(base_temporal)
                    desired.update(desired_temporal)

            if input.recurrence is not None:
                if input.recurrence_scope != "series":
                    raise CalendarValidationError(
                        "recurrence rules require whole-series scope"
                    )
                recurrence = bounded_recurrence_rules(input.recurrence)
                current_recurrence = json.loads(block.recurrence_rules or "[]")
                if not recurrence:
                    raise CalendarValidationError(
                        "stopping a series is outside the bounded surface"
                    )
                if recurrence != current_recurrence:
                    changed_fields.append("recurrence")
                    base["recurrence"] = current_recurrence
                    desired["recurrence"] = recurrence

            if not changed_fields:
                raise CalendarValidationError("no_change_requested")

            intent_id = str(uuid4())
            sequence = 1 if latest is None else latest.sequence + 1
            changed_fields_json = _json(changed_fields)
            connection.execute(
                insert(calendar_provider_write_intents).values(
                    id=intent_id,
                    command_id=input.command_id,
                    calendar_block_id=block.id,
                    account_id=link.account_id,
                    calendar_id=link.calendar_id,
                    provider_event_id=link.provider_event_id,
                    sequence=sequence,
                    predecessor_intent_id=predecessor_id,
                    operation="patch",
                    recurrence_scope=input.recurrence_scope,
                    changed_fields_json=changed_fields_json,
                    base_values_json=_json(base),
                    desired_values_json=_json(desired),
                    expected_provider_etag=link.provider_etag,
                    source_block_revision=block.revision,
                    schema_version=1,
                    state="queued",
                    attempt_count=0,
                    next_attempt_at=None,
                    last_attempt_at=None,
                    failure_class=None,
                    failure_reason=None,
                    created_at=now,
                    updated_at=now,
                    resolved_at=None,
                    prune_after=None,
                    provenance=input.provenance,
                )
            )
            queued = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            _canonical_audit(
                connection,
                block_id=block.id,
                action=f"{input.edit_kind}_requested",
                command_id=input.command_id,
                from_revision=block.revision,
                to_revision=block.revision,
            )
            _audit(
                connection,
                queued,
                action="write_intent_queued",
                from_state=None,
                to_state="queued",
                occurred_at=now,
                executor_provenance="direct_human",
            )
            if initial_state == "queued":
                # Held behind genuinely in-flight provider work. The owner is
                # not waiting on this: the local projection already shows it.
                return _summary(queued)
            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == intent_id)
                .values(state="ready", updated_at=now)
            )
            ready = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            _audit(
                connection,
                ready,
                action="write_intent_ready",
                from_state="queued",
                to_state="ready",
                occurred_at=now,
                executor_provenance="direct_human",
            )
            return _summary(ready)

    def delete(
        self, input: DeleteProviderEventInput
    ) -> ProviderWriteIntentSummaryOutput | None:
        """Persist a delete intent or cancel a never-attempted create locally."""
        now = utc_now()
        expected_operation = (
            "cancel_occurrence"
            if input.recurrence_scope == "occurrence"
            else "delete_series"
            if input.recurrence_scope == "series"
            # A `this and following` delete is a bounded master trim, never a
            # per-occurrence deletion sweep.
            else "patch"
            if input.recurrence_scope == "this_and_following"
            else "delete_event"
        )
        with self.engine.begin() as connection:
            local_cancel = connection.execute(
                select(audit_events.c.event_id).where(
                    audit_events.c.command_id == input.command_id,
                    audit_events.c.action == "create_cancelled_locally",
                    audit_events.c.entity_id == input.calendar_block_id,
                )
            ).one_or_none()
            if local_cancel is not None:
                return None
            existing_command = connection.execute(
                select(calendar_provider_write_intents).where(
                    calendar_provider_write_intents.c.command_id == input.command_id
                )
            ).one_or_none()
            if existing_command is not None:
                if existing_command.operation != expected_operation or (
                    input.recurrence_scope == "single"
                    and existing_command.calendar_block_id != input.calendar_block_id
                ):
                    raise CalendarConflictError(input.command_id)
                return _summary(existing_command)

            selected_block = self._required_row(
                connection, calendar_blocks, input.calendar_block_id
            )
            if selected_block.revision != input.expected_block_revision:
                raise CalendarConflictError(input.calendar_block_id)
            if input.recurrence_scope == "this_and_following":
                return self._split_series(
                    connection, selected_block, input, now, removes_following=True
                )
            block, link, exception_block_id = self._recurrence_target(
                connection,
                selected_block,
                input.recurrence_scope,
                input.occurrence_original_start,
            )
            account = self._required_row(connection, google_accounts, link.account_id)
            calendar = self._required_row(
                connection, google_calendars, link.calendar_id
            )
            metadata = self._required_row(
                connection,
                calendar_block_ion_metadata,
                selected_block.id,
                calendar_block_ion_metadata.c.calendar_block_id,
            )
            if metadata.flexibility == "locked" and not input.locked_confirmed:
                raise CalendarValidationError("locked_confirmation_required")

            latest = connection.execute(
                select(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.calendar_block_id == block.id)
                .order_by(calendar_provider_write_intents.c.sequence.desc())
                .limit(1)
            ).one_or_none()
            if latest is not None and _predecessor_blocks_new_write(
                latest, input.recurrence_scope, input.occurrence_original_start
            ):
                if (
                    latest.operation == "create"
                    and latest.state in ("queued", "ready")
                    and latest.attempt_count == 0
                    and link.link_state == "pending_create"
                    and input.recurrence_scope == "single"
                ):
                    connection.execute(
                        update(calendar_provider_write_intents)
                        .where(calendar_provider_write_intents.c.id == latest.id)
                        .values(
                            state="cancelled",
                            failure_class=None,
                            failure_reason="cancelled_before_provider_attempt",
                            updated_at=now,
                            resolved_at=now,
                        )
                    )
                    cancelled = self._required_row(
                        connection, calendar_provider_write_intents, latest.id
                    )
                    connection.execute(
                        update(calendar_blocks)
                        .where(calendar_blocks.c.id == block.id)
                        .values(
                            status="cancelled",
                            provider_deleted_at=now,
                            updated_at=now,
                            revision=block.revision + 1,
                        )
                    )
                    _audit(
                        connection,
                        cancelled,
                        action="write_cancelled",
                        from_state=latest.state,
                        to_state="cancelled",
                        occurred_at=now,
                        executor_provenance="direct_human",
                        resulting_revision=block.revision + 1,
                    )
                    _canonical_audit(
                        connection,
                        block_id=block.id,
                        action="create_cancelled_locally",
                        command_id=input.command_id,
                        from_revision=block.revision,
                        to_revision=block.revision + 1,
                    )
                    return None
                if latest.operation == "create":
                    raise CalendarValidationError("create_reconciliation_required")
                # Deleting is a direct human action like any other: accept it,
                # superseding an obsolete unattempted write or waiting behind a
                # genuinely in-flight one.
                delete_predecessor, delete_state = self._supersede_or_chain(
                    connection, latest, now
                )
            else:
                delete_predecessor, delete_state = None, "ready"

            reason = _write_reason(
                account,
                calendar,
                link,
                block,
                allow_recurrence=input.recurrence_scope != "single",
            )
            if reason != "eligible":
                raise CalendarValidationError(reason)
            if selected_block.id != block.id:
                selected_link = self._required_row(
                    connection,
                    google_event_links,
                    selected_block.id,
                    google_event_links.c.calendar_block_id,
                )
                selected_reason = _write_reason(
                    account,
                    calendar,
                    selected_link,
                    selected_block,
                    allow_recurrence=True,
                )
                if selected_reason != "eligible":
                    raise CalendarValidationError(selected_reason)
            intent_id = str(uuid4())
            sequence = 1 if latest is None else latest.sequence + 1
            base = {"schema_version": 1, "status": selected_block.status}
            if input.recurrence_scope == "occurrence":
                base["recurrence_identity"] = ProviderRecurrenceIdentity(
                    master_provider_event_id=link.provider_event_id,
                    master_provider_etag=link.provider_etag,
                    original_start=input.occurrence_original_start,
                    exception_calendar_block_id=exception_block_id,
                ).model_dump(mode="json", exclude_none=True)
            desired = {"schema_version": 1, "status": "cancelled"}
            operation = expected_operation
            connection.execute(
                insert(calendar_provider_write_intents).values(
                    id=intent_id,
                    command_id=input.command_id,
                    calendar_block_id=block.id,
                    account_id=link.account_id,
                    calendar_id=link.calendar_id,
                    provider_event_id=link.provider_event_id,
                    sequence=sequence,
                    predecessor_intent_id=delete_predecessor,
                    operation=operation,
                    recurrence_scope=input.recurrence_scope,
                    changed_fields_json=_json(["status"]),
                    base_values_json=_json(base),
                    desired_values_json=_json(desired),
                    expected_provider_etag=link.provider_etag,
                    source_block_revision=block.revision,
                    schema_version=1,
                    state="queued",
                    attempt_count=0,
                    next_attempt_at=None,
                    last_attempt_at=None,
                    failure_class=None,
                    failure_reason=None,
                    created_at=now,
                    updated_at=now,
                    resolved_at=None,
                    prune_after=None,
                    provenance=input.provenance,
                )
            )
            queued = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            _canonical_audit(
                connection,
                block_id=block.id,
                action=(
                    "occurrence_cancel_requested"
                    if input.recurrence_scope == "occurrence"
                    else "series_delete_requested"
                    if input.recurrence_scope == "series"
                    else "delete_requested"
                ),
                command_id=input.command_id,
                from_revision=block.revision,
                to_revision=block.revision,
            )
            _audit(
                connection,
                queued,
                action="write_intent_queued",
                from_state=None,
                to_state="queued",
                occurred_at=now,
                executor_provenance="direct_human",
            )
            if delete_state == "queued":
                return _summary(queued)
            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == intent_id)
                .values(state="ready", updated_at=now)
            )
            ready = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            _audit(
                connection,
                ready,
                action="write_intent_ready",
                from_state="queued",
                to_state="ready",
                occurred_at=now,
                executor_provenance="direct_human",
            )
            return _summary(ready)

    def _rebase_or_conflict(self, connection, row, event, revision, now):
        """Re-arm a pending intent against freshly confirmed provider state.

        Ordinary ETag drift is not a decision for the user. Confirmed provider
        state has just been re-read and stored, so the intent adopts that fresh
        ETag -- and, for an occurrence, the fresh master ETag its recurrence
        identity preflights against -- and retries. Field ownership falls out of
        the existing narrow model rather than any merge rule of its own: the
        provider body carries only `changed_fields`, so Google's edits to every
        other field survive, and the pending direct-human value wins its own
        field for this settlement cycle.

        The rebase is bounded by the same automatic attempt budget as any other
        retry. Exhausting it is the honest signal that this is not ordinary
        drift, and only then does it become a human decision.
        """
        if row.attempt_count >= MAX_AUTOMATIC_ATTEMPTS:
            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == row.id)
                .values(
                    state="conflict",
                    failure_class="stale_precondition",
                    failure_reason="automatic_rebase_exhausted",
                    updated_at=now,
                )
            )
            conflict = self._required_row(
                connection, calendar_provider_write_intents, row.id
            )
            _audit(
                connection,
                conflict,
                action="write_conflict_detected",
                from_state=row.state,
                to_state="conflict",
                occurred_at=now,
                executor_provenance="recovery",
                resulting_revision=revision,
            )
            return _summary(conflict)

        base_values_json = row.base_values_json
        if row.recurrence_scope == "occurrence" and base_values_json:
            # An occurrence intent embeds the master ETag inside its identity,
            # and `begin_attempt` preflights that value. Rebasing the row's own
            # ETag without it would fail preflight and re-enter this path.
            master_link = connection.execute(
                select(google_event_links).where(
                    google_event_links.c.calendar_block_id == row.calendar_block_id
                )
            ).one_or_none()
            stored = json.loads(base_values_json)
            identity = stored.get("recurrence_identity")
            if master_link is not None and identity is not None:
                if not master_link.provider_etag or master_link.provider_etag == "*":
                    raise CalendarValidationError("provider_unconfirmed")
                identity["master_provider_etag"] = master_link.provider_etag
                base_values_json = _json({**stored, "recurrence_identity": identity})

        connection.execute(
            update(calendar_provider_write_intents)
            .where(calendar_provider_write_intents.c.id == row.id)
            .values(
                state="ready",
                expected_provider_etag=event.provider_etag,
                base_values_json=base_values_json,
                next_attempt_at=None,
                failure_class=None,
                failure_reason=None,
                updated_at=now,
            )
        )
        rebased = self._required_row(
            connection, calendar_provider_write_intents, row.id
        )
        _audit(
            connection,
            rebased,
            action="write_intent_ready",
            from_state=row.state,
            to_state="ready",
            occurred_at=now,
            executor_provenance="recovery",
            resulting_revision=revision,
        )
        return _summary(rebased)

    def _supersede_or_chain(self, connection, latest, now: str):
        """Accept a new direct-human mutation while earlier provider work is
        unsettled, and decide how it relates to that work.

        Human interaction and provider dispatch are different concerns. The
        owner may drag the same event three times in a row; the provider still
        gets one serialized write at a time. Refusing the second gesture with
        `write_pending` confused the two and surfaced provider serialization as
        "you cannot edit yet".

        Returns `(predecessor_intent_id, initial_state)` for the new intent.
        """
        if latest is None or latest.state in TERMINAL_PREDECESSOR_STATES:
            return None, "ready"
        if latest.state not in NONTERMINAL_INTENT_STATES:
            # A resolved-but-reviewable outcome (conflict/failed). The newer
            # human action is the owner's answer to it, so it supersedes.
            return None, "ready"
        if latest.state in ("attempting", "ambiguous"):
            # Genuinely in flight, or of unknown provider outcome. Never cancel
            # it and never dispatch a parallel write to the same target: the
            # newer intent waits durably and is released -- and re-aimed at
            # whatever authority that attempt confirms -- once it settles.
            return latest.id, "queued"

        # `queued`, `ready`, or `retry_wait`: nothing is in flight, so the older
        # desired value is simply obsolete. Retire it rather than spending a
        # provider round-trip on a position the owner has already moved past.
        # Its audit evidence is untouched.
        connection.execute(
            update(calendar_provider_write_intents)
            .where(calendar_provider_write_intents.c.id == latest.id)
            .values(
                state="cancelled",
                failure_class=None,
                failure_reason="superseded_by_newer_human_intent",
                next_attempt_at=None,
                updated_at=now,
                resolved_at=now,
            )
        )
        superseded = self._required_row(
            connection, calendar_provider_write_intents, latest.id
        )
        _audit(
            connection,
            superseded,
            action="write_cancelled",
            from_state=latest.state,
            to_state="cancelled",
            occurred_at=now,
            executor_provenance="direct_human",
        )
        # If the obsolete intent was itself waiting behind an in-flight write,
        # the replacement inherits that place in the queue.
        if latest.predecessor_intent_id is not None:
            return latest.predecessor_intent_id, "queued"
        return None, "ready"

    def _settle_dependent_intent(
        self, connection, predecessor_id: str, predecessor_state: str, occurred_at: str
    ) -> None:
        """Release or retire a queued dependent once its predecessor settles.

        A `this and following` split's new master must only ever be dispatched
        after the old master's trim is genuinely provider-confirmed. A trim that
        was cancelled instead -- by Keep Google, or by discarding the pending
        intent -- must never leave the new future series behind to be created
        against an untrimmed series, so it is retired with it.
        """
        dependent = connection.execute(
            select(calendar_provider_write_intents)
            .where(
                calendar_provider_write_intents.c.predecessor_intent_id
                == predecessor_id,
                calendar_provider_write_intents.c.state == "queued",
            )
            .order_by(calendar_provider_write_intents.c.sequence)
            .limit(1)
        ).one_or_none()
        if dependent is None:
            return
        predecessor = self._required_row(
            connection, calendar_provider_write_intents, predecessor_id
        )
        # Two different things use this chain, distinguished by their target. A
        # split's second half writes a *different* block and is only meaningful
        # if the trim confirmed. A superseding human edit writes the *same*
        # block: it is an independent instruction the owner already gave, so it
        # is released however the earlier attempt turned out -- and re-aimed at
        # whatever authority that attempt left behind.
        supersedes_same_target = (
            dependent.calendar_block_id == predecessor.calendar_block_id
        )
        released = supersedes_same_target or predecessor_state == "completed"
        rebased_etag = dependent.expected_provider_etag
        rebased_base_json = dependent.base_values_json
        if released and supersedes_same_target:
            # The write it waited on just moved provider authority. Re-aim the
            # dependent now, so the plan handed to the dispatcher is already
            # correct rather than relying on the preflight to repair it.
            link = connection.execute(
                select(google_event_links).where(
                    google_event_links.c.calendar_block_id
                    == dependent.calendar_block_id
                )
            ).one_or_none()
            if link is not None and link.provider_etag and link.provider_etag != "*":
                rebased_etag = link.provider_etag
                if dependent.recurrence_scope == "occurrence" and rebased_base_json:
                    stored = json.loads(rebased_base_json)
                    identity = stored.get("recurrence_identity")
                    if identity is not None:
                        stored["recurrence_identity"] = {
                            **identity,
                            "master_provider_etag": link.provider_etag,
                        }
                        rebased_base_json = _json(stored)
        connection.execute(
            update(calendar_provider_write_intents)
            .where(calendar_provider_write_intents.c.id == dependent.id)
            .values(
                state="ready" if released else "cancelled",
                expected_provider_etag=rebased_etag,
                base_values_json=rebased_base_json,
                updated_at=occurred_at,
                resolved_at=None if released else occurred_at,
                failure_reason=None if released else "series_split_abandoned",
            )
        )
        settled = self._required_row(
            connection, calendar_provider_write_intents, dependent.id
        )
        _audit(
            connection,
            settled,
            action="write_intent_ready" if released else "write_cancelled",
            from_state="queued",
            to_state="ready" if released else "cancelled",
            occurred_at=occurred_at,
            executor_provenance="recovery",
        )

    def _split_series(
        self, connection, selected_block, input, now, *, removes_following=False
    ):
        """Google-parity `this and following`: one durable local intention that
        becomes two ordered provider operations -- conditionally trim the old
        master so it stops before the selected occurrence, then create a new
        recurring master that begins at it.

        Both operations, the new canonical master, its Ion metadata, and its
        deterministic provider identity are persisted in this single
        transaction, before any Google call, so a crash or restart can never
        lose the intent or produce a duplicate future series.
        """
        master, master_link, _exception_block_id = self._recurrence_target(
            connection, selected_block, "occurrence", input.occurrence_original_start
        )
        account = self._required_row(
            connection, google_accounts, master_link.account_id
        )
        calendar = self._required_row(
            connection, google_calendars, master_link.calendar_id
        )
        reason = _write_reason(
            account, calendar, master_link, master, allow_recurrence=True
        )
        if reason != "eligible":
            raise CalendarValidationError(reason)
        metadata = self._required_row(
            connection,
            calendar_block_ion_metadata,
            master.id,
            calendar_block_ion_metadata.c.calendar_block_id,
        )
        # Splitting to *edit* the following occurrences preserves them all, so it
        # needs no confirmation. Splitting to *delete* them removes confirmed
        # occurrences and keeps the explicit confirmation.
        if (
            removes_following
            and metadata.flexibility == "locked"
            and not input.locked_confirmed
        ):
            raise CalendarValidationError("locked_confirmation_required")

        preset, original_start = self._split_preconditions(
            connection, master, master_link, input.occurrence_original_start
        )

        latest = connection.execute(
            select(calendar_provider_write_intents)
            .where(calendar_provider_write_intents.c.calendar_block_id == master.id)
            .order_by(calendar_provider_write_intents.c.sequence.desc())
            .limit(1)
        ).one_or_none()
        # A split changes structure, so it is never coalesced away -- but the
        # owner is still not refused. Where earlier work is unsettled the trim
        # waits durably behind it, and the split's own new master stays chained
        # behind the trim, so the ordering stays truthful.
        split_predecessor: str | None = None
        split_state = "ready"
        if latest is not None and _predecessor_blocks_new_write(latest, "series", None):
            if latest.state in ("attempting", "ambiguous"):
                split_predecessor, split_state = latest.id, "queued"
            else:
                split_predecessor, split_state = self._supersede_or_chain(
                    connection, latest, now
                )

        # --- The old master's bounded, domain-generated termination. ---
        trim_rules = terminated_recurrence_rules(
            preset, series_trim_until(master, original_start)
        )
        current_rules = json.loads(master.recurrence_rules or "[]")
        trim_sequence = 1 if latest is None else latest.sequence + 1
        trim_id = str(uuid4())
        connection.execute(
            insert(calendar_provider_write_intents).values(
                id=trim_id,
                command_id=input.command_id,
                calendar_block_id=master.id,
                account_id=master_link.account_id,
                calendar_id=master_link.calendar_id,
                provider_event_id=master_link.provider_event_id,
                sequence=trim_sequence,
                predecessor_intent_id=split_predecessor,
                operation="patch",
                recurrence_scope="series",
                changed_fields_json=_json(["recurrence"]),
                base_values_json=_json(
                    {"schema_version": 1, "recurrence": current_rules}
                ),
                desired_values_json=_json(
                    {"schema_version": 1, "recurrence": trim_rules}
                ),
                expected_provider_etag=master_link.provider_etag,
                source_block_revision=master.revision,
                schema_version=1,
                state="queued",
                attempt_count=0,
                next_attempt_at=None,
                last_attempt_at=None,
                failure_class=None,
                failure_reason=None,
                created_at=now,
                updated_at=now,
                resolved_at=None,
                prune_after=None,
                provenance="direct_human",
            )
        )
        queued_trim = self._required_row(
            connection, calendar_provider_write_intents, trim_id
        )
        _canonical_audit(
            connection,
            block_id=master.id,
            action="series_split_requested",
            command_id=input.command_id,
            from_revision=master.revision,
            to_revision=master.revision,
        )
        _audit(
            connection,
            queued_trim,
            action="write_intent_queued",
            from_state=None,
            to_state="queued",
            occurred_at=now,
            executor_provenance="direct_human",
        )
        if split_state == "queued":
            # The trim waits behind genuinely in-flight work; the new master
            # still waits behind the trim.
            return _summary(queued_trim)
        connection.execute(
            update(calendar_provider_write_intents)
            .where(calendar_provider_write_intents.c.id == trim_id)
            .values(state="ready", updated_at=now)
        )
        ready_trim = self._required_row(
            connection, calendar_provider_write_intents, trim_id
        )
        _audit(
            connection,
            ready_trim,
            action="write_intent_ready",
            from_state="queued",
            to_state="ready",
            occurred_at=now,
            executor_provenance="direct_human",
        )

        if removes_following:
            # Deleting this and following is expressed entirely by the trim:
            # the desired future state is absence, so no new master is created
            # and no future occurrence is patched individually.
            return _summary(ready_trim)

        # --- The new future master, durable before any provider call. ---
        new_block_id = str(uuid4())
        new_provider_event_id = deterministic_google_event_id(new_block_id)
        temporal, provider_temporal = self._split_new_master_temporal(
            master, original_start, input
        )
        title = (input.title or master.title).strip() or UNTITLED_EVENT
        forward_rules = bounded_recurrence_rules(preset)
        connection.execute(
            insert(calendar_blocks).values(
                id=new_block_id,
                source_kind="google",
                title=title,
                description=None,
                location=None,
                status="confirmed",
                transparency=master.transparency,
                recurrence_kind="master",
                recurrence_rules=_json(forward_rules),
                recurrence_master_block_id=None,
                provider_deleted_at=None,
                created_at=now,
                updated_at=now,
                revision=1,
                trashed_at=None,
                **temporal,
            )
        )
        # Ion-only organisational metadata follows the series across the split;
        # provider identity, ETag, and write state deliberately do not.
        connection.execute(
            insert(calendar_block_ion_metadata).values(
                calendar_block_id=new_block_id,
                flexibility=metadata.flexibility,
                notes=metadata.notes,
                category=metadata.category,
                category_subtype=metadata.category_subtype,
                created_at=now,
                updated_at=now,
                revision=1,
            )
        )
        connection.execute(
            insert(google_event_links).values(
                calendar_block_id=new_block_id,
                account_id=master_link.account_id,
                calendar_id=master_link.calendar_id,
                provider_event_id=new_provider_event_id,
                ical_uid=None,
                provider_etag=None,
                provider_updated_at=None,
                recurring_event_id=None,
                original_start_kind="none",
                original_start_date=None,
                original_start_at=None,
                original_start_timezone=None,
                last_seen_sync_generation=None,
                link_state="pending_create",
                provider_event_type="default",
                provider_locked=False,
                has_attendees=False,
            )
        )
        create_id = str(uuid4())
        connection.execute(
            insert(calendar_provider_write_intents).values(
                id=create_id,
                command_id=str(uuid4()),
                calendar_block_id=new_block_id,
                account_id=master_link.account_id,
                calendar_id=master_link.calendar_id,
                provider_event_id=new_provider_event_id,
                sequence=1,
                # Ordering is durable, not in-memory: the new master cannot be
                # selected for dispatch until the trim is provider-confirmed.
                predecessor_intent_id=trim_id,
                operation="create",
                recurrence_scope="series",
                changed_fields_json=_json(
                    ["title", "transparency", "temporal", "recurrence"]
                ),
                base_values_json=None,
                desired_values_json=_json(
                    {
                        "schema_version": 1,
                        "title": title,
                        "transparency": master.transparency,
                        **provider_temporal,
                        "recurrence": forward_rules,
                    }
                ),
                expected_provider_etag=None,
                source_block_revision=1,
                schema_version=1,
                state="queued",
                attempt_count=0,
                next_attempt_at=None,
                last_attempt_at=None,
                failure_class=None,
                failure_reason=None,
                created_at=now,
                updated_at=now,
                resolved_at=None,
                prune_after=None,
                provenance="direct_human",
            )
        )
        queued_create = self._required_row(
            connection, calendar_provider_write_intents, create_id
        )
        _canonical_audit(
            connection,
            block_id=new_block_id,
            action="series_split_requested",
            command_id=input.command_id,
            from_revision=None,
            to_revision=1,
        )
        _audit(
            connection,
            queued_create,
            action="write_intent_queued",
            from_state=None,
            to_state="queued",
            occurred_at=now,
            executor_provenance="direct_human",
        )
        return _summary(ready_trim)

    def _split_preconditions(self, connection, master, master_link, original_start):
        """A split is offered only where Ion can faithfully continue the
        series, and only where it means something distinct from `All events`."""
        if master.recurrence_kind != "master":
            raise CalendarValidationError("recurrence_identity_unresolved")
        preset = bounded_recurrence_preset(json.loads(master.recurrence_rules or "[]"))
        if preset is None or preset == "none":
            # A custom provider RRULE is preserved, never approximated.
            raise CalendarValidationError("recurrence_split_unsupported")
        if not master_link.provider_etag or master_link.provider_etag == "*":
            raise CalendarValidationError("provider_unconfirmed")
        if original_start is None:
            raise CalendarValidationError("recurrence_identity_unresolved")
        # Splitting at the first occurrence would produce an empty old series;
        # that is exactly `All events`, so it is refused rather than performed.
        if _same_original_start(_block_start_provider_time(master), original_start):
            raise CalendarValidationError("recurrence_split_at_first_occurrence")
        return preset, original_start

    def _split_new_master_temporal(self, master, original_start, input):
        """The new master starts at the selected occurrence, carrying either the
        requested edit or the occurrence's own confirmed time."""
        base = _occurrence_temporal_contract(master, original_start)
        if master.temporal_kind == "all_day":
            start_date = input.start_date or base["start"]["date"]
            end_date = input.end_date or base["end"]["date"]
            if end_date <= start_date:
                raise CalendarValidationError("all-day end must follow start")
            return (
                {
                    "temporal_kind": "all_day",
                    "start_date": start_date,
                    "end_date": end_date,
                    "start_at": None,
                    "end_at": None,
                    "start_timezone": None,
                    "end_timezone": None,
                },
                {"start": {"date": start_date}, "end": {"date": end_date}},
            )
        zone = master.start_timezone
        if input.timezone is not None and input.timezone != zone:
            raise CalendarValidationError("timezone_change_unsupported")
        base_start = _parse_timestamp(base["start"]["date_time"])
        base_end = _parse_timestamp(base["end"]["date_time"])
        if input.start_date and input.start_time:
            start = _resolved_wall_time(input.start_date, input.start_time, zone)
        else:
            start = base_start
        if input.edit_kind == "move":
            end = (start.astimezone(UTC) + (base_end - base_start)).astimezone(
                _validated_zone(zone)
            )
        elif input.end_date and input.end_time:
            end = _resolved_wall_time(input.end_date, input.end_time, zone)
        else:
            end = base_end
        if end <= start:
            raise CalendarValidationError("timed end must be after start")
        series_zone = _validated_zone(zone)
        start = start.astimezone(series_zone)
        end = end.astimezone(series_zone)
        return (
            {
                "temporal_kind": "timed",
                "start_date": None,
                "end_date": None,
                "start_at": start.isoformat(timespec="seconds"),
                "end_at": end.isoformat(timespec="seconds"),
                "start_timezone": zone,
                "end_timezone": master.end_timezone or zone,
            },
            {
                "start": {
                    "date_time": start.isoformat(timespec="seconds"),
                    "timezone": zone,
                },
                "end": {
                    "date_time": end.isoformat(timespec="seconds"),
                    "timezone": master.end_timezone or zone,
                },
            },
        )

    def _resolvable_intent_for_block(
        self, connection, selected_block, *, required_states: tuple[str, ...]
    ):
        """Find the intent that a human conflict-resolution action on
        `selected_block` concerns, in `required_state`.

        This must select exactly what `CalendarService._block_output`
        *displays* for the same row, or a block can render "needs review"
        forever while every resolution action reports that there is nothing
        to resolve. The projection reads the highest-sequence intent on the
        block's canonical write target (the master, for an exception row),
        and an exception row shows it only when that write targets that
        exact occurrence. So:

        - exception row: the latest intent targeting this occurrence's own
          immutable original start (siblings carry independent intents, see
          `_predecessor_blocks_new_write`);
        - master or single row: simply the latest intent by sequence,
          whatever its scope. A conflicted occurrence never materializes an
          exception row, so its conflict is displayed on -- and must be
          resolvable from -- the master itself.
        """
        serialization_block_id = (
            selected_block.recurrence_master_block_id
            if selected_block.recurrence_kind == "exception"
            else selected_block.id
        )
        candidates = connection.execute(
            select(calendar_provider_write_intents)
            .where(
                calendar_provider_write_intents.c.calendar_block_id
                == serialization_block_id
            )
            .order_by(calendar_provider_write_intents.c.sequence.desc())
        ).all()
        if selected_block.recurrence_kind == "exception":
            selected_link = self._required_row(
                connection,
                google_event_links,
                selected_block.id,
                google_event_links.c.calendar_block_id,
            )
            target_original_start = _provider_time_from_link(selected_link)
            for row in candidates:
                if row.recurrence_scope != "occurrence":
                    continue
                base = ProviderWriteValues.model_validate_json(row.base_values_json)
                identity = base.recurrence_identity
                if identity is None or identity.original_start is None:
                    continue
                if _same_original_start(target_original_start, identity.original_start):
                    if row.state not in required_states:
                        raise CalendarValidationError("no_conflict_to_resolve")
                    return row
            raise CalendarValidationError("no_conflict_to_resolve")
        if not candidates or candidates[0].state not in required_states:
            raise CalendarValidationError("no_conflict_to_resolve")
        return candidates[0]

    def keep_google_version(
        self, input: KeepGoogleVersionInput
    ) -> ProviderWriteIntentSummaryOutput:
        """Discard the pending provider-field intent and keep the latest
        confirmed Google values. Ion-only metadata and unrelated blocks are
        untouched; this only cancels the conflicted intent row."""
        now = utc_now()
        with self.engine.begin() as connection:
            selected_block = self._required_row(
                connection, calendar_blocks, input.calendar_block_id
            )
            if selected_block.revision != input.expected_block_revision:
                raise CalendarConflictError(input.calendar_block_id)
            conflicted = self._resolvable_intent_for_block(
                connection, selected_block, required_states=RESOLVABLE_INTENT_STATES
            )
            resolution_reason = (
                "conflict_resolved_keep_google"
                if conflicted.state == "conflict"
                else "failed_intent_discarded_by_human"
            )
            connection.execute(
                update(calendar_provider_write_intents)
                .where(
                    calendar_provider_write_intents.c.id == conflicted.id,
                    calendar_provider_write_intents.c.state == conflicted.state,
                )
                .values(
                    state="cancelled",
                    failure_reason=resolution_reason,
                    updated_at=now,
                    resolved_at=now,
                )
            )
            changed = self._required_row(
                connection, calendar_provider_write_intents, conflicted.id
            )
            _audit(
                connection,
                changed,
                action="write_cancelled",
                from_state=conflicted.state,
                to_state="cancelled",
                occurred_at=now,
                executor_provenance="direct_human",
            )
            # Discarding a series-split trim discards its future master too:
            # creating it against an untrimmed series would duplicate events.
            self._settle_dependent_intent(connection, conflicted.id, "cancelled", now)
            return _summary(changed)

    def apply_ion_changes(
        self, input: ApplyIonChangesInput
    ) -> ProviderWriteIntentSummaryOutput:
        """Rebase the conflicted intent's field mask onto the freshly
        confirmed provider ETag as a new explicit human write authorization.
        Never reuses the stale conflict row's ETag and never `If-Match: *`."""
        now = utc_now()
        with self.engine.begin() as connection:
            existing_command = connection.execute(
                select(calendar_provider_write_intents).where(
                    calendar_provider_write_intents.c.command_id == input.command_id
                )
            ).one_or_none()
            if existing_command is not None:
                if existing_command.predecessor_intent_id is None:
                    raise CalendarConflictError(input.command_id)
                return _summary(existing_command)

            selected_block = self._required_row(
                connection, calendar_blocks, input.calendar_block_id
            )
            if selected_block.revision != input.expected_block_revision:
                raise CalendarConflictError(input.calendar_block_id)
            conflicted = self._resolvable_intent_for_block(
                connection, selected_block, required_states=RESOLVABLE_INTENT_STATES
            )
            recurrence_scope = conflicted.recurrence_scope
            conflicted_base = (
                ProviderWriteValues.model_validate_json(conflicted.base_values_json)
                if conflicted.base_values_json
                else None
            )
            original_start = None
            if recurrence_scope == "occurrence":
                original_start = conflicted_base.recurrence_identity.original_start
            master, master_link, exception_block_id = self._recurrence_target(
                connection, selected_block, recurrence_scope, original_start
            )
            account = self._required_row(
                connection, google_accounts, master_link.account_id
            )
            calendar = self._required_row(
                connection, google_calendars, master_link.calendar_id
            )
            reason = _write_reason(
                account,
                calendar,
                master_link,
                master,
                allow_recurrence=recurrence_scope != "single",
            )
            if reason != "eligible":
                raise CalendarValidationError(reason)
            if not master_link.provider_etag or master_link.provider_etag == "*":
                raise CalendarValidationError("provider_unconfirmed")

            # Rebase every piece of provider authority the new write carries,
            # not just the row's own ETag. An occurrence intent also embeds the
            # master ETag inside its recurrence identity, and `begin_attempt`
            # preflights *that* value against the confirmed link. Copying the
            # conflicted row's stale identity made the rebased write fail its
            # own preflight and immediately re-conflict, so the change never
            # reached Google. Identity (master event ID, immutable original
            # start, exception linkage) is preserved exactly; only the
            # confirmed authority is refreshed.
            base_values_json = conflicted.base_values_json
            if recurrence_scope == "occurrence":
                rebased_identity = ProviderRecurrenceIdentity(
                    master_provider_event_id=master_link.provider_event_id,
                    master_provider_etag=master_link.provider_etag,
                    original_start=conflicted_base.recurrence_identity.original_start,
                    exception_calendar_block_id=exception_block_id
                    or conflicted_base.recurrence_identity.exception_calendar_block_id,
                )
                base_values_json = _json(
                    {
                        **json.loads(conflicted.base_values_json),
                        "recurrence_identity": rebased_identity.model_dump(
                            mode="json", exclude_none=True
                        ),
                    }
                )

            intent_id = str(uuid4())
            sequence = conflicted.sequence + 1
            connection.execute(
                insert(calendar_provider_write_intents).values(
                    id=intent_id,
                    command_id=input.command_id,
                    calendar_block_id=master.id,
                    account_id=master_link.account_id,
                    calendar_id=master_link.calendar_id,
                    provider_event_id=master_link.provider_event_id,
                    sequence=sequence,
                    predecessor_intent_id=conflicted.id,
                    operation=conflicted.operation,
                    recurrence_scope=recurrence_scope,
                    changed_fields_json=conflicted.changed_fields_json,
                    base_values_json=base_values_json,
                    desired_values_json=conflicted.desired_values_json,
                    expected_provider_etag=master_link.provider_etag,
                    source_block_revision=selected_block.revision,
                    schema_version=1,
                    state="queued",
                    attempt_count=0,
                    next_attempt_at=None,
                    last_attempt_at=None,
                    failure_class=None,
                    failure_reason=None,
                    created_at=now,
                    updated_at=now,
                    resolved_at=None,
                    prune_after=None,
                    provenance="direct_human",
                )
            )
            queued = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            _audit(
                connection,
                queued,
                action="write_intent_queued",
                from_state=None,
                to_state="queued",
                occurred_at=now,
                executor_provenance="direct_human",
            )
            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == intent_id)
                .values(state="ready", updated_at=now)
            )
            ready = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            _audit(
                connection,
                ready,
                action="write_intent_ready",
                from_state="queued",
                to_state="ready",
                occurred_at=now,
                executor_provenance="direct_human",
            )
            connection.execute(
                update(calendar_provider_write_intents)
                .where(
                    calendar_provider_write_intents.c.id == conflicted.id,
                    calendar_provider_write_intents.c.state == conflicted.state,
                )
                .values(
                    state="cancelled",
                    failure_reason=(
                        "conflict_resolved_apply_ion"
                        if conflicted.state == "conflict"
                        else "failed_intent_reauthorized_by_human"
                    ),
                    updated_at=now,
                    resolved_at=now,
                )
            )
            # A split's queued future master follows the re-authorized trim
            # instead of being retired with the superseded one.
            connection.execute(
                update(calendar_provider_write_intents)
                .where(
                    calendar_provider_write_intents.c.predecessor_intent_id
                    == conflicted.id,
                    calendar_provider_write_intents.c.state == "queued",
                )
                .values(predecessor_intent_id=intent_id, updated_at=now)
            )
            resolved_predecessor = self._required_row(
                connection, calendar_provider_write_intents, conflicted.id
            )
            _audit(
                connection,
                resolved_predecessor,
                action="write_cancelled",
                from_state=conflicted.state,
                to_state="cancelled",
                occurred_at=now,
                executor_provenance="direct_human",
            )
            return _summary(ready)

    def review_differences(self, calendar_block_id: str) -> ReviewDifferencesOutput:
        """Read-only bounded comparison between the latest confirmed
        provider values and the preserved Ion desired intent. No raw
        provider object, technical ID, or ETag is exposed."""
        with self.engine.connect() as connection:
            selected_block = self._required_row(
                connection, calendar_blocks, calendar_block_id
            )
            conflicted = self._resolvable_intent_for_block(
                connection, selected_block, required_states=RESOLVABLE_INTENT_STATES
            )
            changed_fields = json.loads(conflicted.changed_fields_json)
            desired = (
                json.loads(conflicted.desired_values_json)
                if conflicted.desired_values_json
                else {}
            )
            output: dict[str, object] = {
                "calendar_block_id": calendar_block_id,
                "changed_fields": changed_fields,
            }
            if "title" in changed_fields:
                output["confirmed_title"] = selected_block.title
                output["desired_title"] = desired.get("title")
            if "temporal" in changed_fields:
                if (
                    conflicted.recurrence_scope == "occurrence"
                    and selected_block.recurrence_kind == "master"
                ):
                    base = ProviderWriteValues.model_validate_json(
                        conflicted.base_values_json
                    )
                    confirmed_temporal = _occurrence_temporal_contract(
                        selected_block, base.recurrence_identity.original_start
                    )
                else:
                    confirmed_temporal = _block_temporal_contract(selected_block)
                output["confirmed_start"] = ProviderDateTime.model_validate(
                    confirmed_temporal["start"]
                )
                output["confirmed_end"] = ProviderDateTime.model_validate(
                    confirmed_temporal["end"]
                )
                output["desired_start"] = ProviderDateTime.model_validate(
                    desired["start"]
                )
                output["desired_end"] = ProviderDateTime.model_validate(desired["end"])
            if "recurrence" in changed_fields:
                output["confirmed_recurrence"] = json.loads(
                    selected_block.recurrence_rules or "[]"
                )
                output["desired_recurrence"] = desired.get("recurrence")
            if "status" in changed_fields:
                output["confirmed_status"] = selected_block.status
                output["desired_status"] = desired.get("status")
            return ReviewDifferencesOutput(**output)

    def queue(
        self, input: QueueProviderWriteIntentInput
    ) -> ProviderWriteIntentSummaryOutput:
        now = utc_now()
        with self.engine.begin() as connection:
            existing = connection.execute(
                select(calendar_provider_write_intents).where(
                    calendar_provider_write_intents.c.command_id == input.command_id
                )
            ).one_or_none()
            if existing is not None:
                return _summary(existing)
            block = self._required_row(
                connection, calendar_blocks, input.calendar_block_id
            )
            if block.revision != input.expected_block_revision:
                raise CalendarConflictError(input.calendar_block_id)
            link = self._required_row(
                connection,
                google_event_links,
                input.calendar_block_id,
                google_event_links.c.calendar_block_id,
            )
            account = self._required_row(connection, google_accounts, link.account_id)
            calendar = self._required_row(
                connection, google_calendars, link.calendar_id
            )
            reason = _write_reason(account, calendar, link, block)
            if input.operation == "create":
                reason = _write_reason(
                    account,
                    calendar,
                    link,
                    block,
                    allow_pending_create=True,
                )
                if reason != "eligible":
                    raise CalendarValidationError(reason)
                if link.link_state != "pending_create":
                    raise CalendarValidationError(
                        "create requires pending provider linkage"
                    )
                expected_id = deterministic_google_event_id(block.id)
                if link.provider_event_id != expected_id:
                    raise CalendarValidationError(
                        "pending create ID is not deterministic"
                    )
            elif reason != "eligible":
                raise CalendarValidationError(reason)
            if input.operation != "create" and not link.provider_etag:
                raise CalendarValidationError("confirmed provider ETag is required")

            latest = connection.execute(
                select(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.calendar_block_id == block.id)
                .order_by(calendar_provider_write_intents.c.sequence.desc())
                .limit(1)
            ).one_or_none()
            intent_id = str(uuid4())
            sequence = 1 if latest is None else latest.sequence + 1
            predecessor = (
                latest.id
                if latest and latest.state not in TERMINAL_PREDECESSOR_STATES
                else None
            )
            changed_fields_json = _json(input.changed_fields)
            connection.execute(
                insert(calendar_provider_write_intents).values(
                    id=intent_id,
                    command_id=input.command_id,
                    calendar_block_id=block.id,
                    account_id=link.account_id,
                    calendar_id=link.calendar_id,
                    provider_event_id=link.provider_event_id,
                    sequence=sequence,
                    predecessor_intent_id=predecessor,
                    operation=input.operation,
                    recurrence_scope=input.recurrence_scope,
                    changed_fields_json=changed_fields_json,
                    base_values_json=_values_json(input.base_values),
                    desired_values_json=_values_json(input.desired_values),
                    expected_provider_etag=link.provider_etag,
                    source_block_revision=block.revision,
                    schema_version=1,
                    state="queued",
                    attempt_count=0,
                    next_attempt_at=None,
                    last_attempt_at=None,
                    failure_class=None,
                    failure_reason=None,
                    created_at=now,
                    updated_at=now,
                    resolved_at=None,
                    prune_after=None,
                    provenance=input.provenance,
                )
            )
            queued = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            _audit(
                connection,
                queued,
                action="write_intent_queued",
                from_state=None,
                to_state="queued",
                occurred_at=now,
                executor_provenance="direct_human",
            )
            if predecessor is None:
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == intent_id)
                    .values(state="ready", updated_at=now)
                )
                ready = self._required_row(
                    connection, calendar_provider_write_intents, intent_id
                )
                _audit(
                    connection,
                    ready,
                    action="write_intent_ready",
                    from_state="queued",
                    to_state="ready",
                    occurred_at=now,
                    executor_provenance="direct_human",
                )
                return _summary(ready)
            return _summary(queued)

    def ready(self, input: ReadyWriteIntentsInput) -> list[ProviderWritePlanOutput]:
        if input.now is not None:
            _canonical_timestamp(input.now)
        with self.engine.connect() as connection:
            active_accounts = set(
                connection.execute(
                    select(calendar_provider_write_intents.c.account_id).where(
                        calendar_provider_write_intents.c.state == "attempting"
                    )
                ).scalars()
            )
            rows = connection.execute(
                select(calendar_provider_write_intents)
                .where(
                    calendar_provider_write_intents.c.state.in_(("ambiguous", "ready"))
                )
                .order_by(
                    calendar_provider_write_intents.c.state != "ambiguous",
                    calendar_provider_write_intents.c.created_at,
                    calendar_provider_write_intents.c.id,
                )
                .limit(input.limit * 4)
            ).all()
            selected = []
            account_ids: set[str] = set()
            for row in rows:
                if row.account_id in account_ids or row.account_id in active_accounts:
                    continue
                if row.predecessor_intent_id:
                    predecessor = self._required_row(
                        connection,
                        calendar_provider_write_intents,
                        row.predecessor_intent_id,
                    )
                    if predecessor.state not in TERMINAL_PREDECESSOR_STATES:
                        continue
                selected.append(_plan(row))
                account_ids.add(row.account_id)
                if len(selected) == input.limit:
                    break
        return selected

    def begin_attempt(
        self, intent_id: str, input: BeginWriteAttemptInput
    ) -> ProviderWriteIntentSummaryOutput:
        now = utc_now()
        with self.engine.begin() as connection:
            row = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            if row.state != input.expected_state:
                raise CalendarConflictError(intent_id)
            if row.operation not in (
                "create",
                "patch",
                "cancel_occurrence",
                "delete_event",
                "delete_series",
            ):
                raise CalendarValidationError(
                    "dispatch accepts only bounded Calendar write operations"
                )
            block = self._required_row(
                connection, calendar_blocks, row.calendar_block_id
            )
            link = self._required_row(
                connection,
                google_event_links,
                row.calendar_block_id,
                google_event_links.c.calendar_block_id,
            )
            account = self._required_row(connection, google_accounts, row.account_id)
            calendar = self._required_row(connection, google_calendars, row.calendar_id)
            reason = _write_reason(
                account,
                calendar,
                link,
                block,
                allow_pending_create=row.operation == "create",
                allow_recurrence=row.recurrence_scope != "single",
            )
            if reason != "eligible":
                target = "reauth_required" if reason == "reauth_required" else "failed"
                failure_class = (
                    "reauthentication_required"
                    if target == "reauth_required"
                    else "provider_not_found"
                    if reason == "calendar_deleted"
                    else "terminal_provider_rejection"
                )
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == row.id)
                    .values(
                        state=target,
                        failure_class=failure_class,
                        failure_reason=reason,
                        updated_at=now,
                    )
                )
                blocked = self._required_row(
                    connection, calendar_provider_write_intents, row.id
                )
                _audit(
                    connection,
                    blocked,
                    action=(
                        "write_reauthentication_required"
                        if target == "reauth_required"
                        else "write_failed_terminally"
                    ),
                    from_state=row.state,
                    to_state=target,
                    occurred_at=now,
                    executor_provenance=input.executor_provenance,
                )
                return _summary(blocked)

            if row.operation != "create" and (
                not row.expected_provider_etag or row.expected_provider_etag == "*"
            ):
                raise CalendarValidationError(
                    "provider mutation requires a bounded non-wildcard ETag"
                )
            recurrence_identity = None
            if row.recurrence_scope == "occurrence":
                base = ProviderWriteValues.model_validate_json(row.base_values_json)
                recurrence_identity = base.recurrence_identity
                if (
                    recurrence_identity is None
                    or row.operation not in ("patch", "cancel_occurrence")
                    or recurrence_identity.master_provider_event_id
                    != link.provider_event_id
                ):
                    raise CalendarValidationError(
                        "occurrence mutation requires canonical recurrence identity"
                    )
                current_etag = recurrence_identity.master_provider_etag
            else:
                if row.recurrence_scope == "series" and row.operation not in (
                    "create",
                    "patch",
                    "delete_series",
                ):
                    raise CalendarValidationError("invalid series mutation")
                current_etag = row.expected_provider_etag
            if row.operation != "create" and link.provider_etag != current_etag:
                # Locally observed drift: a read sync confirmed newer provider
                # state after this intent was armed. That is ordinary, and this
                # is the purest place to absorb it -- the link ETag *is* freshly
                # confirmed authority, so the intent re-aims at it and the
                # attempt proceeds. Conflicting here was the loop the owner hit:
                # Apply my Ion changes armed against the link, a background sync
                # moved the link, and the very next attempt asked for review
                # again without Google ever being contacted.
                if (
                    link.provider_etag
                    and link.provider_etag != "*"
                    and row.attempt_count < MAX_AUTOMATIC_ATTEMPTS
                ):
                    rebased_base_json = row.base_values_json
                    if row.recurrence_scope == "occurrence" and rebased_base_json:
                        stored = json.loads(rebased_base_json)
                        identity = stored.get("recurrence_identity")
                        if identity is not None:
                            identity["master_provider_etag"] = link.provider_etag
                            rebased_base_json = _json(
                                {**stored, "recurrence_identity": identity}
                            )
                    connection.execute(
                        update(calendar_provider_write_intents)
                        .where(calendar_provider_write_intents.c.id == row.id)
                        .values(
                            expected_provider_etag=link.provider_etag,
                            base_values_json=rebased_base_json,
                            updated_at=now,
                        )
                    )
                    row = self._required_row(
                        connection, calendar_provider_write_intents, row.id
                    )
                else:
                    connection.execute(
                        update(calendar_provider_write_intents)
                        .where(calendar_provider_write_intents.c.id == row.id)
                        .values(
                            state="conflict",
                            failure_class="stale_precondition",
                            failure_reason="automatic_rebase_exhausted",
                            updated_at=now,
                        )
                    )
                    conflict = self._required_row(
                        connection, calendar_provider_write_intents, row.id
                    )
                    _audit(
                        connection,
                        conflict,
                        action="write_conflict_detected",
                        from_state=row.state,
                        to_state="conflict",
                        occurred_at=now,
                        executor_provenance=input.executor_provenance,
                    )
                    return _summary(conflict)

            if row.attempt_count >= MAX_AUTOMATIC_ATTEMPTS and row.state != "ambiguous":
                raise CalendarValidationError("automatic attempt limit reached")
            attempt_count = row.attempt_count
            if attempt_count < MAX_AUTOMATIC_ATTEMPTS:
                attempt_count += 1
            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == row.id)
                .values(
                    state="attempting",
                    attempt_count=attempt_count,
                    last_attempt_at=now,
                    next_attempt_at=None,
                    failure_class=None,
                    failure_reason=None,
                    updated_at=now,
                )
            )
            attempting = self._required_row(
                connection, calendar_provider_write_intents, row.id
            )
            _audit(
                connection,
                attempting,
                action="write_attempt_started",
                from_state=row.state,
                to_state="attempting",
                occurred_at=now,
                executor_provenance=input.executor_provenance,
            )
            return _summary(attempting)

    def record_result(
        self, intent_id: str, input: RecordProviderWriteResultInput
    ) -> ProviderWriteIntentSummaryOutput:
        now = utc_now()
        with self.engine.begin() as connection:
            row = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            if row.state != input.expected_state or row.operation not in (
                "create",
                "patch",
                "cancel_occurrence",
                "delete_event",
                "delete_series",
            ):
                raise CalendarConflictError(intent_id)

            result_class = input.result_class
            stored_class = result_class
            next_attempt_at = None
            if result_class == "reauthentication_required":
                target = "reauth_required"
            else:
                if row.operation == "create":
                    if input.stage == "insert" and result_class in (
                        "duplicate_or_ambiguous_create",
                        "retryable_transport",
                    ):
                        target = "ambiguous"
                    elif input.stage == "identity_lookup" and result_class in (
                        "duplicate_or_ambiguous_create",
                        "retryable_transport",
                    ):
                        target = (
                            "failed"
                            if row.attempt_count >= MAX_AUTOMATIC_ATTEMPTS
                            else "ambiguous"
                        )
                    elif (
                        input.stage == "identity_lookup"
                        and result_class == "provider_not_found"
                    ):
                        if row.attempt_count >= MAX_AUTOMATIC_ATTEMPTS:
                            target = "failed"
                        else:
                            target = "retry_wait"
                            stored_class = "retryable_transport"
                    elif result_class in (
                        "retryable_backend",
                        "retryable_quota",
                    ):
                        target = (
                            "failed"
                            if row.attempt_count >= MAX_AUTOMATIC_ATTEMPTS
                            else "retry_wait"
                        )
                    else:
                        target = "failed"
                elif row.operation in ("patch", "cancel_occurrence"):
                    if input.stage == "patch" and result_class == "retryable_transport":
                        target = "ambiguous"
                    elif input.stage == "identity_lookup" and result_class in (
                        "retryable_transport",
                        "retryable_backend",
                    ):
                        target = (
                            "failed"
                            if row.attempt_count >= MAX_AUTOMATIC_ATTEMPTS
                            else "ambiguous"
                        )
                    elif result_class == "stale_precondition":
                        # Google moved underneath this write. Re-read confirmed
                        # state and rebase rather than asking the user to
                        # arbitrate an ordinary edit.
                        target = (
                            "conflict"
                            if row.attempt_count >= MAX_AUTOMATIC_ATTEMPTS
                            else "ambiguous"
                        )
                    elif result_class == "provider_not_found":
                        # Genuinely unmergeable: there is no target left to
                        # rebase onto.
                        target = "conflict"
                    elif (
                        input.stage == "instance_resolution"
                        and result_class == "invalid_target"
                    ):
                        # A provider-rejected occurrence lookup cannot safely be
                        # treated as a generic terminal transport failure. The
                        # durable master/original-start identity needs review.
                        target = "conflict"
                        stored_class = "stale_precondition"
                    elif result_class in (
                        "retryable_backend",
                        "retryable_quota",
                    ):
                        target = (
                            "failed"
                            if row.attempt_count >= MAX_AUTOMATIC_ATTEMPTS
                            else "retry_wait"
                        )
                    else:
                        target = "failed"
                else:
                    if (
                        input.stage == "delete"
                        and result_class == "retryable_transport"
                    ):
                        target = "ambiguous"
                    elif input.stage == "identity_lookup" and result_class in (
                        "retryable_transport",
                        "retryable_backend",
                    ):
                        target = (
                            "failed"
                            if row.attempt_count >= MAX_AUTOMATIC_ATTEMPTS
                            else "ambiguous"
                        )
                    elif result_class == "stale_precondition":
                        target = "conflict"
                    elif result_class == "provider_not_found":
                        target = "failed"
                    elif result_class in ("retryable_backend", "retryable_quota"):
                        target = (
                            "failed"
                            if row.attempt_count >= MAX_AUTOMATIC_ATTEMPTS
                            else "retry_wait"
                        )
                    else:
                        target = "failed"

            if target == "retry_wait":
                delay = full_jitter_delay_seconds(
                    row.attempt_count, self.random_fraction()
                )
                next_attempt_at = (
                    (datetime.now(UTC) + timedelta(seconds=delay))
                    .isoformat(timespec="microseconds")
                    .replace("+00:00", "Z")
                )
            if target == "reauth_required":
                account = self._required_row(
                    connection, google_accounts, row.account_id
                )
                connection.execute(
                    update(google_accounts)
                    .where(google_accounts.c.id == account.id)
                    .values(
                        auth_state="reauth_required",
                        calendar_write_scope_state="reauth_required",
                        updated_at=now,
                        revision=account.revision + 1,
                    )
                )
                connection.execute(
                    update(google_calendars)
                    .where(google_calendars.c.account_id == account.id)
                    .values(sync_state="reauth_required", updated_at=now)
                )

            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == row.id)
                .values(
                    state=target,
                    next_attempt_at=next_attempt_at,
                    failure_class=stored_class,
                    failure_reason=input.safe_reason,
                    updated_at=now,
                )
            )
            changed = self._required_row(
                connection, calendar_provider_write_intents, row.id
            )
            action = {
                "ambiguous": "write_outcome_ambiguous",
                "retry_wait": "write_retry_scheduled",
                "reauth_required": "write_reauthentication_required",
                "conflict": "write_conflict_detected",
                "failed": "write_failed_terminally",
            }[target]
            _audit(
                connection,
                changed,
                action=action,
                from_state=row.state,
                to_state=target,
                occurred_at=now,
                executor_provenance="recovery",
            )
            return _summary(changed)

    def resolve_occurrence(
        self, intent_id: str, input: ResolveProviderOccurrenceInput
    ) -> ProviderWritePlanOutput:
        """Bind one durable occurrence intent to the exact provider instance."""
        now = utc_now()
        with self.engine.begin() as connection:
            row = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            if (
                row.state != input.expected_state
                or row.recurrence_scope != "occurrence"
                or row.operation not in ("patch", "cancel_occurrence")
            ):
                raise CalendarConflictError(intent_id)
            base = ProviderWriteValues.model_validate_json(row.base_values_json)
            identity = base.recurrence_identity
            if identity is None:
                raise CalendarValidationError(
                    "occurrence mutation lacks durable recurrence identity"
                )
            master = input.master
            instance = input.instance
            # Structural identity and eligibility: is this still the same
            # recurring master, and is it still safe to write to? These are
            # genuine contradictions when they fail.
            valid_master = (
                master.provider_event_id == identity.master_provider_event_id
                and master.status != "cancelled"
                and bool(master.recurrence)
                and master.recurring_event_id is None
                and master.provider_event_type == "default"
                and not master.provider_locked
                and not master.has_attendees
            )
            # The master's ETag moving is ordinary sync concurrency, not an
            # identity failure. `master` here was just fetched from the
            # provider, so it *is* fresh confirmed authority: adopt it rather
            # than refusing. Treating this as a conflict was unbounded -- it
            # never consumed an attempt, so every retry and every Apply my Ion
            # changes re-derived the same stale identity and conflicted again.
            master_etag_drifted = (
                valid_master
                and bool(master.provider_etag)
                and master.provider_etag != "*"
                and master.provider_etag != identity.master_provider_etag
            )
            valid_instance = (
                bool(instance.provider_event_id)
                and bool(instance.provider_etag)
                and instance.provider_etag != "*"
                and (
                    row.operation == "cancel_occurrence"
                    or instance.status != "cancelled"
                )
                and not instance.recurrence
                and instance.recurring_event_id == identity.master_provider_event_id
                and instance.original_start is not None
                and _same_original_start(
                    instance.original_start, identity.original_start
                )
                and instance.provider_event_type == "default"
                and not instance.provider_locked
                and not instance.has_attendees
            )
            if not valid_master or not valid_instance:
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == row.id)
                    .values(
                        state="conflict",
                        failure_class="stale_precondition",
                        failure_reason=(
                            "recurrence_master_changed"
                            if not valid_master
                            else "occurrence_identity_changed"
                        ),
                        updated_at=now,
                    )
                )
                conflict = self._required_row(
                    connection, calendar_provider_write_intents, row.id
                )
                _audit(
                    connection,
                    conflict,
                    action="write_conflict_detected",
                    from_state=row.state,
                    to_state="conflict",
                    occurred_at=now,
                    executor_provenance="recovery",
                )
                return _plan(conflict)
            rebased_base_json = row.base_values_json
            if master_etag_drifted:
                # Rebase the embedded master authority in place, and align the
                # confirmed link so the later `begin_attempt` preflight and any
                # sibling occurrence agree with what the provider just told us.
                stored = json.loads(row.base_values_json)
                stored["recurrence_identity"] = {
                    **stored["recurrence_identity"],
                    "master_provider_etag": master.provider_etag,
                }
                rebased_base_json = _json(stored)
                connection.execute(
                    update(google_event_links)
                    .where(
                        google_event_links.c.calendar_block_id == row.calendar_block_id
                    )
                    .values(provider_etag=master.provider_etag)
                )
            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == row.id)
                .values(
                    provider_event_id=instance.provider_event_id,
                    expected_provider_etag=instance.provider_etag,
                    base_values_json=rebased_base_json,
                    updated_at=now,
                )
            )
            resolved = self._required_row(
                connection, calendar_provider_write_intents, row.id
            )
            return _plan(resolved)

    def reconcile_create(
        self, intent_id: str, input: ReconcileProviderCreateInput
    ) -> ProviderWriteIntentSummaryOutput:
        now = utc_now()
        event = input.event
        with self.engine.begin() as connection:
            row = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            if row.state != input.expected_state or row.operation != "create":
                raise CalendarConflictError(intent_id)
            block = self._required_row(
                connection, calendar_blocks, row.calendar_block_id
            )
            self._required_row(
                connection,
                google_event_links,
                row.calendar_block_id,
                google_event_links.c.calendar_block_id,
            )
            desired = ProviderWriteValues.model_validate_json(row.desired_values_json)
            expected_recurrence = desired.recurrence or []
            valid_event = (
                event.provider_event_id == row.provider_event_id
                and bool(event.provider_etag)
                and event.description is None
                and event.location is None
                and event.status == "confirmed"
                and event.start is not None
                and event.end is not None
                and event.recurrence == expected_recurrence
                and event.recurring_event_id is None
                and event.provider_event_type == "default"
                and not event.provider_locked
                and not event.has_attendees
            )
            if valid_event:
                valid_event = _identity_lookup_matches(row, event)
            if not valid_event:
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == row.id)
                    .values(
                        state="conflict",
                        failure_class="stale_precondition",
                        failure_reason="deterministic_id_collision",
                        updated_at=now,
                    )
                )
                conflict = self._required_row(
                    connection, calendar_provider_write_intents, row.id
                )
                _audit(
                    connection,
                    conflict,
                    action="write_conflict_detected",
                    from_state=row.state,
                    to_state="conflict",
                    occurred_at=now,
                    executor_provenance="recovery",
                )
                return _summary(conflict)

            provider_values = {
                "title": event.title or UNTITLED_EVENT,
                "description": event.description,
                "location": event.location,
                "status": event.status,
                "transparency": event.transparency,
                "recurrence_kind": "master" if event.recurrence else "single",
                "recurrence_rules": _json(event.recurrence)
                if event.recurrence
                else None,
                "provider_deleted_at": None,
                **_event_temporal_values(event),
            }
            changed_values = {
                key: value
                for key, value in provider_values.items()
                if getattr(block, key) != value
            }
            revision = block.revision
            if changed_values:
                revision += 1
                connection.execute(
                    update(calendar_blocks)
                    .where(calendar_blocks.c.id == block.id)
                    .values(**changed_values, updated_at=now, revision=revision)
                )
            connection.execute(
                update(google_event_links)
                .where(google_event_links.c.calendar_block_id == block.id)
                .values(
                    ical_uid=event.ical_uid,
                    provider_etag=event.provider_etag,
                    provider_updated_at=event.provider_updated_at,
                    recurring_event_id=None,
                    original_start_kind="none",
                    original_start_date=None,
                    original_start_at=None,
                    original_start_timezone=None,
                    last_seen_sync_generation=row.command_id,
                    link_state="confirmed",
                    provider_event_type="default",
                    provider_locked=False,
                    has_attendees=False,
                )
            )
            prune_after = (
                (datetime.now(UTC) + timedelta(days=COMPLETED_RETENTION_DAYS))
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == row.id)
                .values(
                    state="completed",
                    failure_class="success",
                    failure_reason="provider_confirmed",
                    next_attempt_at=None,
                    updated_at=now,
                    resolved_at=now,
                    prune_after=prune_after,
                )
            )
            completed = self._required_row(
                connection, calendar_provider_write_intents, row.id
            )
            _audit(
                connection,
                completed,
                action="write_completed",
                from_state=row.state,
                to_state="completed",
                occurred_at=now,
                executor_provenance="recovery",
                resulting_revision=revision,
            )
            _canonical_audit(
                connection,
                block_id=block.id,
                action="provider_create_confirmed",
                command_id=row.command_id,
                from_revision=block.revision,
                to_revision=revision,
            )
            return _summary(completed)

    def reconcile_patch(
        self, intent_id: str, input: ReconcileProviderPatchInput
    ) -> ProviderWriteIntentSummaryOutput:
        now = utc_now()
        event = input.event
        with self.engine.begin() as connection:
            row = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            if row.state != input.expected_state or row.operation not in (
                "patch",
                "cancel_occurrence",
            ):
                raise CalendarConflictError(intent_id)
            block = self._required_row(
                connection, calendar_blocks, row.calendar_block_id
            )
            base = ProviderWriteValues.model_validate_json(row.base_values_json)
            identity = base.recurrence_identity
            common_valid = (
                event.provider_event_id == row.provider_event_id
                and bool(event.provider_etag)
                and event.provider_etag != "*"
                and event.provider_event_type == "default"
                and not event.provider_locked
                and not event.has_attendees
            )
            if row.recurrence_scope == "single":
                valid_event = (
                    common_valid
                    and event.status != "cancelled"
                    and event.start is not None
                    and event.end is not None
                    and not event.recurrence
                    and event.recurring_event_id is None
                    and identity is None
                )
            elif row.recurrence_scope == "series":
                valid_event = (
                    common_valid
                    and event.status != "cancelled"
                    and event.start is not None
                    and event.end is not None
                    and bool(event.recurrence)
                    and event.recurring_event_id is None
                    and identity is None
                )
            else:
                valid_event = (
                    common_valid
                    and identity is not None
                    and not event.recurrence
                    and event.recurring_event_id == identity.master_provider_event_id
                    and event.original_start is not None
                    and _same_original_start(
                        event.original_start, identity.original_start
                    )
                    and (
                        (
                            event.status == "cancelled"
                            or (
                                input.resolution_kind == "identity_lookup"
                                and event.status != "cancelled"
                                and event.start is not None
                                and event.end is not None
                            )
                        )
                        if row.operation == "cancel_occurrence"
                        else event.status != "cancelled"
                        and event.start is not None
                        and event.end is not None
                    )
                )
            if not valid_event:
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == row.id)
                    .values(
                        state="conflict",
                        failure_class="stale_precondition",
                        failure_reason="provider_target_changed",
                        updated_at=now,
                    )
                )
                conflict = self._required_row(
                    connection, calendar_provider_write_intents, row.id
                )
                _audit(
                    connection,
                    conflict,
                    action="write_conflict_detected",
                    from_state=row.state,
                    to_state="conflict",
                    occurred_at=now,
                    executor_provenance="recovery",
                )
                return _summary(conflict)

            desired_matches = _event_matches_changed_values(row, event)
            if (
                input.resolution_kind == "identity_lookup"
                and event.provider_etag == row.expected_provider_etag
                and not desired_matches
            ):
                target = (
                    "failed"
                    if row.attempt_count >= MAX_AUTOMATIC_ATTEMPTS
                    else "retry_wait"
                )
                next_attempt_at = None
                if target == "retry_wait":
                    delay = full_jitter_delay_seconds(
                        row.attempt_count, self.random_fraction()
                    )
                    next_attempt_at = (
                        (datetime.now(UTC) + timedelta(seconds=delay))
                        .isoformat(timespec="microseconds")
                        .replace("+00:00", "Z")
                    )
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == row.id)
                    .values(
                        state=target,
                        next_attempt_at=next_attempt_at,
                        failure_class="retryable_transport",
                        failure_reason=(
                            "ambiguous_patch_not_applied"
                            if target == "retry_wait"
                            else "automatic_attempt_limit"
                        ),
                        updated_at=now,
                    )
                )
                changed = self._required_row(
                    connection, calendar_provider_write_intents, row.id
                )
                _audit(
                    connection,
                    changed,
                    action=(
                        "write_retry_scheduled"
                        if target == "retry_wait"
                        else "write_failed_terminally"
                    ),
                    from_state=row.state,
                    to_state=target,
                    occurred_at=now,
                    executor_provenance="recovery",
                )
                return _summary(changed)

            conflict_detected = not desired_matches
            revision = block.revision
            result_block_id = block.id
            if row.recurrence_scope == "occurrence":
                calendar = self._required_row(
                    connection, google_calendars, row.calendar_id
                )
                calendar_service = CalendarService(self.engine)
                calendar_service._reconcile_event(
                    connection, calendar, row.command_id, event
                )
                calendar_service._resolve_recurrence_masters(
                    connection, row.calendar_id
                )
                exception = connection.execute(
                    select(calendar_blocks, google_event_links)
                    .join(
                        google_event_links,
                        google_event_links.c.calendar_block_id == calendar_blocks.c.id,
                    )
                    .where(
                        google_event_links.c.calendar_id == row.calendar_id,
                        google_event_links.c.provider_event_id
                        == event.provider_event_id,
                    )
                ).one_or_none()
                if exception is None:
                    raise CalendarValidationError(
                        "provider occurrence reconciliation failed"
                    )
                if (
                    identity.exception_calendar_block_id is not None
                    and exception.id != identity.exception_calendar_block_id
                ):
                    conflict_detected = True
                result_block_id = exception.id
                revision = exception.revision
            else:
                provider_values = {
                    "title": event.title or UNTITLED_EVENT,
                    "description": event.description,
                    "location": event.location,
                    "status": event.status,
                    "transparency": event.transparency,
                    "recurrence_kind": (
                        "master" if row.recurrence_scope == "series" else "single"
                    ),
                    "recurrence_rules": (
                        _json(event.recurrence)
                        if row.recurrence_scope == "series"
                        else None
                    ),
                    "provider_deleted_at": None,
                    **_event_temporal_values(event),
                }
                changed_values = {
                    key: value
                    for key, value in provider_values.items()
                    if getattr(block, key) != value
                }
                if changed_values:
                    revision += 1
                    connection.execute(
                        update(calendar_blocks)
                        .where(calendar_blocks.c.id == block.id)
                        .values(**changed_values, updated_at=now, revision=revision)
                    )
                connection.execute(
                    update(google_event_links)
                    .where(google_event_links.c.calendar_block_id == block.id)
                    .values(
                        ical_uid=event.ical_uid,
                        provider_etag=event.provider_etag,
                        provider_updated_at=event.provider_updated_at,
                        link_state="confirmed",
                        provider_event_type="default",
                        provider_locked=False,
                        has_attendees=False,
                    )
                )

            if conflict_detected:
                # Automatic convergence. Confirmed provider state was just
                # re-read and stored above, so the pending intent re-arms
                # against that fresh ETag and retries its own narrow field
                # mask. Because the provider body carries only the fields the
                # user actually changed, Google's independent edits to other
                # fields survive untouched, and the user's pending field wins
                # for this settlement cycle -- after which normal read-sync
                # makes later Google changes authoritative again.
                return self._rebase_or_conflict(connection, row, event, revision, now)

            prune_after = (
                (datetime.now(UTC) + timedelta(days=COMPLETED_RETENTION_DAYS))
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == row.id)
                .values(
                    state="completed",
                    failure_class="success",
                    failure_reason="provider_confirmed",
                    next_attempt_at=None,
                    updated_at=now,
                    resolved_at=now,
                    prune_after=prune_after,
                )
            )
            completed = self._required_row(
                connection, calendar_provider_write_intents, row.id
            )
            _audit(
                connection,
                completed,
                action="write_completed",
                from_state=row.state,
                to_state="completed",
                occurred_at=now,
                executor_provenance="recovery",
                resulting_revision=revision,
            )
            self._settle_dependent_intent(connection, row.id, "completed", now)
            _canonical_audit(
                connection,
                block_id=result_block_id,
                action=(
                    "provider_occurrence_cancel_confirmed"
                    if row.operation == "cancel_occurrence"
                    else "provider_occurrence_patch_confirmed"
                    if row.recurrence_scope == "occurrence"
                    else "provider_series_patch_confirmed"
                    if row.recurrence_scope == "series"
                    else "provider_patch_confirmed"
                ),
                command_id=row.command_id,
                from_revision=(
                    None if row.recurrence_scope == "occurrence" else block.revision
                ),
                to_revision=revision,
            )
            return _summary(completed)

    def reconcile_delete(
        self, intent_id: str, input: ReconcileProviderDeleteInput
    ) -> ProviderWriteIntentSummaryOutput:
        now = utc_now()
        with self.engine.begin() as connection:
            row = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            if row.state != input.expected_state or row.operation not in (
                "delete_event",
                "delete_series",
            ):
                raise CalendarConflictError(intent_id)
            block = self._required_row(
                connection, calendar_blocks, row.calendar_block_id
            )
            if input.resolution_kind == "identity_lookup":
                event = input.event
                valid = (
                    event is not None
                    and event.provider_event_id == row.provider_event_id
                    and bool(event.provider_etag)
                    and event.provider_etag != "*"
                    and event.status != "cancelled"
                    and event.provider_event_type == "default"
                    and not event.provider_locked
                    and not event.has_attendees
                    and (
                        bool(event.recurrence)
                        if row.operation == "delete_series"
                        else not event.recurrence
                    )
                    and event.recurring_event_id is None
                )
                if not valid or event.provider_etag != row.expected_provider_etag:
                    connection.execute(
                        update(calendar_provider_write_intents)
                        .where(calendar_provider_write_intents.c.id == row.id)
                        .values(
                            state="conflict",
                            failure_class="stale_precondition",
                            failure_reason="provider_target_changed",
                            updated_at=now,
                        )
                    )
                    changed = self._required_row(
                        connection, calendar_provider_write_intents, row.id
                    )
                    _audit(
                        connection,
                        changed,
                        action="write_conflict_detected",
                        from_state=row.state,
                        to_state="conflict",
                        occurred_at=now,
                        executor_provenance="recovery",
                    )
                    return _summary(changed)
                target = (
                    "failed"
                    if row.attempt_count >= MAX_AUTOMATIC_ATTEMPTS
                    else "retry_wait"
                )
                next_attempt_at = None
                if target == "retry_wait":
                    delay = full_jitter_delay_seconds(
                        row.attempt_count, self.random_fraction()
                    )
                    next_attempt_at = (
                        (datetime.now(UTC) + timedelta(seconds=delay))
                        .isoformat(timespec="microseconds")
                        .replace("+00:00", "Z")
                    )
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == row.id)
                    .values(
                        state=target,
                        next_attempt_at=next_attempt_at,
                        failure_class="retryable_transport",
                        failure_reason=(
                            "ambiguous_delete_not_applied"
                            if target == "retry_wait"
                            else "automatic_attempt_limit"
                        ),
                        updated_at=now,
                    )
                )
                changed = self._required_row(
                    connection, calendar_provider_write_intents, row.id
                )
                _audit(
                    connection,
                    changed,
                    action="write_retry_scheduled"
                    if target == "retry_wait"
                    else "write_failed_terminally",
                    from_state=row.state,
                    to_state=target,
                    occurred_at=now,
                    executor_provenance="recovery",
                )
                return _summary(changed)

            revision = block.revision + 1
            connection.execute(
                update(calendar_blocks)
                .where(calendar_blocks.c.id == block.id)
                .values(
                    status="cancelled",
                    provider_deleted_at=now,
                    updated_at=now,
                    revision=revision,
                )
            )
            if row.operation == "delete_series":
                connection.execute(
                    update(calendar_blocks)
                    .where(calendar_blocks.c.recurrence_master_block_id == block.id)
                    .values(
                        status="cancelled",
                        provider_deleted_at=now,
                        updated_at=now,
                        revision=calendar_blocks.c.revision + 1,
                    )
                )
            prune_after = (
                (datetime.now(UTC) + timedelta(days=COMPLETED_RETENTION_DAYS))
                .isoformat(timespec="microseconds")
                .replace("+00:00", "Z")
            )
            reason = (
                "provider_already_absent"
                if input.resolution_kind == "already_absent"
                else "provider_confirmed"
            )
            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == row.id)
                .values(
                    state="completed",
                    failure_class="success",
                    failure_reason=reason,
                    next_attempt_at=None,
                    updated_at=now,
                    resolved_at=now,
                    prune_after=prune_after,
                )
            )
            completed = self._required_row(
                connection, calendar_provider_write_intents, row.id
            )
            _audit(
                connection,
                completed,
                action="write_completed",
                from_state=row.state,
                to_state="completed",
                occurred_at=now,
                executor_provenance="recovery",
                resulting_revision=revision,
            )
            _canonical_audit(
                connection,
                block_id=block.id,
                action=(
                    "provider_series_delete_already_absent"
                    if row.operation == "delete_series"
                    and input.resolution_kind == "already_absent"
                    else "provider_series_delete_confirmed"
                    if row.operation == "delete_series"
                    else "provider_delete_already_absent"
                    if input.resolution_kind == "already_absent"
                    else "provider_delete_confirmed"
                ),
                command_id=row.command_id,
                from_revision=block.revision,
                to_revision=revision,
            )
            return _summary(completed)

    def transition(
        self, intent_id: str, input: WriteIntentTransitionInput
    ) -> ProviderWriteIntentSummaryOutput:
        occurred = _parse_timestamp(input.occurred_at)
        occurred_at = _canonical_timestamp(input.occurred_at)
        next_attempt_at = (
            _canonical_timestamp(input.next_attempt_at)
            if input.next_attempt_at is not None
            else None
        )
        with self.engine.begin() as connection:
            row = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            if row.state != input.expected_state:
                raise CalendarConflictError(intent_id)
            if input.target_state not in ALLOWED_TRANSITIONS[row.state]:
                raise CalendarValidationError("invalid provider-write state transition")
            attempt_count = row.attempt_count
            last_attempt_at = row.last_attempt_at
            if input.target_state == "attempting":
                if attempt_count >= MAX_AUTOMATIC_ATTEMPTS:
                    raise CalendarValidationError("automatic attempt limit reached")
                attempt_count += 1
                last_attempt_at = occurred_at
            if (
                input.target_state == "retry_wait"
                and attempt_count >= MAX_AUTOMATIC_ATTEMPTS
            ):
                raise CalendarValidationError("final attempt cannot schedule retry")
            resolved_at = None
            prune_after = None
            if input.target_state in ("completed", "cancelled"):
                resolved_at = occurred_at
                if input.target_state == "completed":
                    prune_after = (
                        (occurred + timedelta(days=COMPLETED_RETENTION_DAYS))
                        .isoformat(timespec="microseconds")
                        .replace("+00:00", "Z")
                    )
            connection.execute(
                update(calendar_provider_write_intents)
                .where(
                    calendar_provider_write_intents.c.id == intent_id,
                    calendar_provider_write_intents.c.state == row.state,
                )
                .values(
                    state=input.target_state,
                    attempt_count=attempt_count,
                    next_attempt_at=next_attempt_at,
                    last_attempt_at=last_attempt_at,
                    failure_class=input.result_class,
                    failure_reason=input.safe_reason,
                    updated_at=occurred_at,
                    resolved_at=resolved_at,
                    prune_after=prune_after,
                )
            )
            changed = self._required_row(
                connection, calendar_provider_write_intents, intent_id
            )
            action = {
                "attempting": "write_attempt_started",
                "retry_wait": "write_retry_scheduled",
                "reauth_required": "write_reauthentication_required",
                "ambiguous": "write_outcome_ambiguous",
                "conflict": "write_conflict_detected",
                "failed": "write_failed_terminally",
                "completed": "write_completed",
                "cancelled": "write_cancelled",
                "ready": "write_intent_ready",
            }[input.target_state]
            _audit(
                connection,
                changed,
                action=action,
                from_state=row.state,
                to_state=input.target_state,
                occurred_at=occurred_at,
                executor_provenance=input.executor_provenance,
                resulting_revision=input.resulting_revision,
            )
            # A superseding human edit must also be released when the write it
            # waited on ended in conflict or terminal failure, not only when it
            # completed -- otherwise the owner's newest instruction is stranded.
            if input.target_state in TERMINAL_PREDECESSOR_STATES or (
                input.target_state in RESOLVABLE_INTENT_STATES
            ):
                self._settle_dependent_intent(
                    connection, intent_id, input.target_state, occurred_at
                )
            return _summary(changed)

    def recover(self, input: RecoverWriteIntentsInput) -> RecoveryResultOutput:
        now = _canonical_timestamp(input.now) if input.now is not None else utc_now()
        attempting_count = 0
        retry_count = 0
        reauth_count = 0
        failed_occurrence_count = 0
        legacy_count = 0
        with self.engine.begin() as connection:
            attempting = connection.execute(
                select(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.state == "attempting")
                .order_by(calendar_provider_write_intents.c.updated_at)
                .limit(input.limit)
            ).all()
            for row in attempting:
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == row.id)
                    .values(
                        state="ambiguous",
                        failure_class=(
                            "duplicate_or_ambiguous_create"
                            if row.operation == "create"
                            else "retryable_transport"
                        ),
                        failure_reason="restart_after_attempt",
                        updated_at=now,
                    )
                )
                repaired = self._required_row(
                    connection, calendar_provider_write_intents, row.id
                )
                _audit(
                    connection,
                    repaired,
                    action="write_outcome_ambiguous",
                    from_state="attempting",
                    to_state="ambiguous",
                    occurred_at=now,
                    executor_provenance="recovery",
                )
                attempting_count += 1

            remaining = input.limit - attempting_count
            if remaining > 0:
                due = connection.execute(
                    select(calendar_provider_write_intents)
                    .where(
                        calendar_provider_write_intents.c.state == "retry_wait",
                        calendar_provider_write_intents.c.next_attempt_at <= now,
                    )
                    .order_by(calendar_provider_write_intents.c.next_attempt_at)
                    .limit(remaining)
                ).all()
                for row in due:
                    connection.execute(
                        update(calendar_provider_write_intents)
                        .where(calendar_provider_write_intents.c.id == row.id)
                        .values(state="ready", next_attempt_at=None, updated_at=now)
                    )
                    promoted = self._required_row(
                        connection, calendar_provider_write_intents, row.id
                    )
                    _audit(
                        connection,
                        promoted,
                        action="write_intent_ready",
                        from_state="retry_wait",
                        to_state="ready",
                        occurred_at=now,
                        executor_provenance="recovery",
                    )
                    retry_count += 1
            remaining = input.limit - attempting_count - retry_count
            if remaining > 0:
                reauthorized = connection.execute(
                    select(calendar_provider_write_intents)
                    .join(
                        google_accounts,
                        google_accounts.c.id
                        == calendar_provider_write_intents.c.account_id,
                    )
                    .where(
                        calendar_provider_write_intents.c.state == "reauth_required",
                        google_accounts.c.auth_state == "connected",
                        google_accounts.c.calendar_write_scope_state == "write_granted",
                    )
                    .order_by(calendar_provider_write_intents.c.updated_at)
                    .limit(remaining)
                ).all()
                for row in reauthorized:
                    connection.execute(
                        update(calendar_provider_write_intents)
                        .where(calendar_provider_write_intents.c.id == row.id)
                        .values(
                            state="ready",
                            failure_class=None,
                            failure_reason=None,
                            updated_at=now,
                        )
                    )
                    promoted = self._required_row(
                        connection, calendar_provider_write_intents, row.id
                    )
                    _audit(
                        connection,
                        promoted,
                        action="write_intent_ready",
                        from_state="reauth_required",
                        to_state="ready",
                        occurred_at=now,
                        executor_provenance="recovery",
                    )
                    reauth_count += 1
            remaining = input.limit - attempting_count - retry_count - reauth_count
            if remaining > 0:
                legacy_failed = connection.execute(
                    select(
                        calendar_provider_write_intents,
                        google_event_links.c.provider_etag.label(
                            "current_provider_etag"
                        ),
                    )
                    .join(
                        google_event_links,
                        google_event_links.c.calendar_block_id
                        == calendar_provider_write_intents.c.calendar_block_id,
                    )
                    .where(
                        calendar_provider_write_intents.c.state == "failed",
                        calendar_provider_write_intents.c.operation.in_(
                            ("patch", "cancel_occurrence")
                        ),
                        calendar_provider_write_intents.c.recurrence_scope
                        == "occurrence",
                        calendar_provider_write_intents.c.failure_class
                        == "invalid_target",
                        calendar_provider_write_intents.c.failure_reason
                        == "provider_rejected_target",
                    )
                    .order_by(calendar_provider_write_intents.c.updated_at)
                    .limit(remaining)
                ).all()
                for row in legacy_failed:
                    base = ProviderWriteValues.model_validate_json(row.base_values_json)
                    identity = base.recurrence_identity
                    if (
                        identity is None
                        or row.provider_event_id != identity.master_provider_event_id
                        or not row.current_provider_etag
                        or row.current_provider_etag == identity.master_provider_etag
                    ):
                        continue
                    # The master moved since that resolution failed, so the
                    # rejection describes a target that no longer exists. Re-arm
                    # the owner's intent against the confirmed master and let
                    # the automatic rebase try again. Recovery must never
                    # *manufacture* a review task out of ordinary drift -- that
                    # is the obsolete policy running on every dispatch.
                    stored = json.loads(row.base_values_json)
                    stored["recurrence_identity"] = {
                        **stored["recurrence_identity"],
                        "master_provider_etag": row.current_provider_etag,
                    }
                    connection.execute(
                        update(calendar_provider_write_intents)
                        .where(calendar_provider_write_intents.c.id == row.id)
                        .values(
                            state="ready",
                            base_values_json=_json(stored),
                            attempt_count=0,
                            failure_class=None,
                            failure_reason=None,
                            next_attempt_at=None,
                            updated_at=now,
                        )
                    )
                    rearmed = self._required_row(
                        connection, calendar_provider_write_intents, row.id
                    )
                    _audit(
                        connection,
                        rearmed,
                        action="write_intent_ready",
                        from_state="failed",
                        to_state="ready",
                        occurred_at=now,
                        executor_provenance="recovery",
                    )
                    failed_occurrence_count += 1
            # Safety net for a superseding human edit whose predecessor settled
            # through a path that did not release it directly. The owner's
            # newest instruction must never be stranded because the write it
            # waited on ended somewhere unexpected.
            stranded = connection.execute(
                select(calendar_provider_write_intents)
                .where(
                    calendar_provider_write_intents.c.state == "queued",
                    calendar_provider_write_intents.c.predecessor_intent_id.is_not(
                        None
                    ),
                )
                .limit(input.limit)
            ).all()
            for row in stranded:
                predecessor = connection.execute(
                    select(calendar_provider_write_intents).where(
                        calendar_provider_write_intents.c.id
                        == row.predecessor_intent_id
                    )
                ).one_or_none()
                if predecessor is None:
                    continue
                if predecessor.state in NONTERMINAL_INTENT_STATES:
                    continue
                if row.calendar_block_id != predecessor.calendar_block_id:
                    # A split's second half keeps its stricter rule.
                    continue
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == row.id)
                    .values(state="ready", updated_at=now)
                )
                released_row = self._required_row(
                    connection, calendar_provider_write_intents, row.id
                )
                _audit(
                    connection,
                    released_row,
                    action="write_intent_ready",
                    from_state="queued",
                    to_state="ready",
                    occurred_at=now,
                    executor_provenance="recovery",
                )

            # Rows conflicted by the superseded policy describe ordinary drift,
            # which the product no longer treats as a human decision. Re-arm
            # them against confirmed authority so an owner upgrading into the
            # new behavior is not left holding a permanent "needs review".
            # Audit evidence of the original conflict is untouched.
            legacy = connection.execute(
                select(calendar_provider_write_intents, google_event_links)
                .join(
                    google_event_links,
                    google_event_links.c.calendar_block_id
                    == calendar_provider_write_intents.c.calendar_block_id,
                )
                .where(
                    calendar_provider_write_intents.c.state == "conflict",
                    calendar_provider_write_intents.c.failure_class
                    == "stale_precondition",
                    calendar_provider_write_intents.c.failure_reason.in_(
                        LEGACY_ORDINARY_DRIFT_REASONS
                    ),
                    calendar_provider_write_intents.c.attempt_count
                    < MAX_AUTOMATIC_ATTEMPTS,
                )
                .limit(input.limit)
            ).all()
            for row in legacy:
                if not row.provider_etag or row.provider_etag == "*":
                    continue
                rebased_base_json = row.base_values_json
                if row.recurrence_scope == "occurrence" and rebased_base_json:
                    stored = json.loads(rebased_base_json)
                    stored_identity = stored.get("recurrence_identity")
                    if stored_identity is None:
                        # Not enough durable evidence to rebase safely; leave
                        # it explicit rather than guessing at its target.
                        continue
                    stored["recurrence_identity"] = {
                        **stored_identity,
                        "master_provider_etag": row.provider_etag,
                    }
                    rebased_base_json = _json(stored)
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == row.id)
                    .values(
                        state="ready",
                        expected_provider_etag=row.provider_etag,
                        base_values_json=rebased_base_json,
                        failure_class=None,
                        failure_reason=None,
                        next_attempt_at=None,
                        updated_at=now,
                    )
                )
                requeued = self._required_row(
                    connection, calendar_provider_write_intents, row.id
                )
                _audit(
                    connection,
                    requeued,
                    action="write_intent_ready",
                    from_state="conflict",
                    to_state="ready",
                    occurred_at=now,
                    executor_provenance="recovery",
                )
                legacy_count += 1

            # Anything still waiting after this pass is waiting on the clock
            # alone. Reporting when it becomes due lets the dispatcher wake
            # itself once, so an ordinary retry never needs a manual sync.
            waiting = connection.execute(
                select(func.min(calendar_provider_write_intents.c.next_attempt_at))
                .where(calendar_provider_write_intents.c.state == "retry_wait")
                .where(calendar_provider_write_intents.c.next_attempt_at.is_not(None))
            ).scalar_one_or_none()
        return RecoveryResultOutput(
            attempting_to_ambiguous=attempting_count,
            retry_wait_to_ready=retry_count,
            reauth_required_to_ready=reauth_count,
            failed_occurrence_to_conflict=failed_occurrence_count,
            legacy_conflicts_requeued=legacy_count,
            next_retry_in_seconds=_seconds_until(waiting, now),
        )

    def prune(self, input: PruneWriteIntentsInput) -> PruneResultOutput:
        now = _canonical_timestamp(input.now)
        with self.engine.begin() as connection:
            eligible = (
                connection.execute(
                    select(calendar_provider_write_intents.c.id)
                    .where(
                        calendar_provider_write_intents.c.state == "completed",
                        calendar_provider_write_intents.c.prune_after.is_not(None),
                        calendar_provider_write_intents.c.prune_after <= now,
                        select(func.count(calendar_provider_write_audit.c.id))
                        .where(
                            calendar_provider_write_audit.c.intent_id
                            == calendar_provider_write_intents.c.id
                        )
                        .scalar_subquery()
                        > 0,
                        select(func.count(google_event_links.c.calendar_block_id))
                        .where(
                            google_event_links.c.calendar_block_id
                            == calendar_provider_write_intents.c.calendar_block_id,
                            google_event_links.c.link_state == "confirmed",
                        )
                        .scalar_subquery()
                        > 0,
                    )
                    .order_by(calendar_provider_write_intents.c.prune_after)
                    .limit(input.limit)
                )
                .scalars()
                .all()
            )
            if eligible:
                connection.execute(
                    delete(calendar_provider_write_intents).where(
                        calendar_provider_write_intents.c.id.in_(eligible)
                    )
                )
        return PruneResultOutput(pruned=len(eligible))
