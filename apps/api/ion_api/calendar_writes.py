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
    CalendarValidationError,
)
from ion_api.calendar_write_contracts import (
    AccountWriteCapabilityOutput,
    BeginWriteAttemptInput,
    BlockWriteCapabilityOutput,
    CalendarWriteCapabilityOutput,
    CalendarWriteFoundationOutput,
    CreateProviderEventInput,
    ProviderWriteIntentSummaryOutput,
    ProviderWritePlanOutput,
    PruneResultOutput,
    PruneWriteIntentsInput,
    QueueProviderWriteIntentInput,
    ReadyWriteIntentsInput,
    ReconcileProviderCreateInput,
    RecordProviderWriteResultInput,
    RecoverWriteIntentsInput,
    RecoveryResultOutput,
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
TERMINAL_PREDECESSOR_STATES = ("completed", "cancelled")
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
    "ambiguous": frozenset(("attempting", "conflict", "failed", "cancelled")),
    "conflict": frozenset(("cancelled",)),
    "failed": frozenset(("cancelled",)),
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
    account, calendar, link=None, block=None, *, allow_pending_create=False
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
    connection.execute(
        insert(audit_events).values(
            event_id=str(uuid4()),
            occurred_at=utc_now(),
            entity_type="calendar_block",
            entity_id=block_id,
            action=action,
            actor_kind="human" if action == "create_requested" else "integration",
            authority="direct" if action == "create_requested" else "approved",
            source="desktop" if action == "create_requested" else "google_calendar",
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
    from ion_api.calendar_contracts import ProviderDateTime

    return _same_provider_time(
        event.start, ProviderDateTime.model_validate(expected_start)
    ) and _same_provider_time(event.end, ProviderDateTime.model_validate(expected_end))


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
                    eligible=(
                        _write_reason(
                            account_by_id[link.account_id],
                            calendar_by_id[link.calendar_id],
                            link,
                            block_by_id[link.calendar_block_id],
                        )
                        == "eligible"
                    ),
                    reason=_write_reason(
                        account_by_id[link.account_id],
                        calendar_by_id[link.calendar_id],
                        link,
                        block_by_id[link.calendar_block_id],
                    ),
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
            changed_fields_json = _json(changed_fields)
            desired_values_json = _json(
                {
                    "schema_version": 1,
                    "title": title,
                    "transparency": "opaque",
                    **provider_temporal,
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
                    recurrence_kind="single",
                    recurrence_rules=None,
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
                    recurrence_scope="single",
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
            if row.operation != "create":
                raise CalendarValidationError("Phase 2C-2 dispatch accepts create only")
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
                account, calendar, link, block, allow_pending_create=True
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
            if row.state != input.expected_state or row.operation != "create":
                raise CalendarConflictError(intent_id)

            result_class = input.result_class
            stored_class = result_class
            next_attempt_at = None
            if result_class == "reauthentication_required":
                target = "reauth_required"
            elif input.stage == "insert" and result_class in (
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
            valid_event = (
                event.provider_event_id == row.provider_event_id
                and bool(event.provider_etag)
                and event.description is None
                and event.location is None
                and event.status == "confirmed"
                and event.start is not None
                and event.end is not None
                and not event.recurrence
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
                "recurrence_kind": "single",
                "recurrence_rules": None,
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
            if input.target_state in TERMINAL_PREDECESSOR_STATES:
                successor = connection.execute(
                    select(calendar_provider_write_intents)
                    .where(
                        calendar_provider_write_intents.c.predecessor_intent_id
                        == intent_id,
                        calendar_provider_write_intents.c.state == "queued",
                    )
                    .order_by(calendar_provider_write_intents.c.sequence)
                    .limit(1)
                ).one_or_none()
                if successor:
                    connection.execute(
                        update(calendar_provider_write_intents)
                        .where(calendar_provider_write_intents.c.id == successor.id)
                        .values(state="ready", updated_at=occurred_at)
                    )
                    promoted = self._required_row(
                        connection, calendar_provider_write_intents, successor.id
                    )
                    _audit(
                        connection,
                        promoted,
                        action="write_intent_ready",
                        from_state="queued",
                        to_state="ready",
                        occurred_at=occurred_at,
                        executor_provenance="recovery",
                    )
            return _summary(changed)

    def recover(self, input: RecoverWriteIntentsInput) -> RecoveryResultOutput:
        now = _canonical_timestamp(input.now) if input.now is not None else utc_now()
        attempting_count = 0
        retry_count = 0
        reauth_count = 0
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
        return RecoveryResultOutput(
            attempting_to_ambiguous=attempting_count,
            retry_wait_to_ready=retry_count,
            reauth_required_to_ready=reauth_count,
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
