"""Durable, provider-free Phase 2C-1 Calendar write foundation."""

from __future__ import annotations

import base64
import hashlib
import json
import math
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from sqlalchemy import Engine, delete, func, insert, select, update

from ion_api.calendar import (
    CalendarConflictError,
    CalendarNotFoundError,
    CalendarValidationError,
)
from ion_api.calendar_write_contracts import (
    AccountWriteCapabilityOutput,
    BlockWriteCapabilityOutput,
    CalendarWriteCapabilityOutput,
    CalendarWriteFoundationOutput,
    ProviderWriteIntentSummaryOutput,
    ProviderWritePlanOutput,
    PruneResultOutput,
    PruneWriteIntentsInput,
    QueueProviderWriteIntentInput,
    ReadyWriteIntentsInput,
    RecoverWriteIntentsInput,
    RecoveryResultOutput,
    WriteIntentTransitionInput,
)
from ion_api.schema import (
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
    if not calendar.enabled_in_ion:
        return "calendar_disabled"
    if calendar.provider_deleted:
        return "calendar_deleted"
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


class CalendarWriteService:
    def __init__(self, engine: Engine):
        self.engine = engine

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
                .where(calendar_provider_write_intents.c.state == "ready")
                .order_by(
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
        now = _canonical_timestamp(input.now)
        attempting_count = 0
        retry_count = 0
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
        return RecoveryResultOutput(
            attempting_to_ambiguous=attempting_count,
            retry_wait_to_ready=retry_count,
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
