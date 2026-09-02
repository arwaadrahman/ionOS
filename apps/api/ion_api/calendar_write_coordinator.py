"""Phase 2C-R0 direct-human write coordinator.

This module exists to make one architectural claim true and testable:

> **Human intent acceptance and provider write execution are separate concerns.**

Phase 2C v1 conflated them. Provider serialization surfaced to the owner as
"you cannot edit yet" (`write_pending`), and any unclassified provider
disagreement could fall through into a generic review task. Both are structural
here rather than matters of care:

* :meth:`CalendarWriteCoordinator.accept_direct_human_intent` has **no provider
  precondition at all**. It cannot consult, wait for, or be refused by provider
  state, because it never reads it. A direct human action is the authorization
  (docs/CALENDAR_BEHAVIOR.md), so acceptance is durable and unconditional.
* Serialization lives entirely in :meth:`select_provider_work`, which is the
  read side of a separate lane. Its `provider_busy` flag exists so the
  dispatcher can serialize, never so a person can be refused.
* Recovery classification is total over the closed taxonomy in
  :mod:`ion_api.calendar_write_model`, so no outcome can produce a generic
  "review this" state.

R0 dispatches nothing. Provider execution is modelled, transitioned, recovered,
and tested, but no operation is dispatchable until R1 adds a real dispatch path
behind its own real-Google acceptance gate.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from uuid import uuid4

from sqlalchemy import Engine, and_, func, insert, select, update

from ion_api.calendar_write_contracts import (
    DirectHumanEditDraft,
    DirectHumanIntentInput,
    DirectHumanIntentReceipt,
    ProviderWorkOutput,
    ProviderWritePlan,
    RecoveryEntry,
    RecoveryOutput,
)
from ion_api.calendar_write_model import (
    ACCEPTED_OPERATIONS,
    ACCEPTED_RECURRENCE_SCOPES,
    CHANGED_FIELDS,
    COORDINATOR_UNUSED_STATES,
    DISPATCHABLE_OPERATIONS,
    MAX_ATTEMPTS,
    CalendarWriteVocabularyError,
    classify_failure,
    is_automatically_recoverable,
    requires_owner_action,
)
from ion_api.schema import (
    calendar_blocks,
    calendar_provider_write_audit,
    calendar_provider_write_intents,
    google_accounts,
    google_calendars,
    google_event_links,
)

#: States in which an intent has not settled and still owns its target.
UNRESOLVED_STATES = (
    "queued",
    "ready",
    "attempting",
    "retry_wait",
    "reauth_required",
    "ambiguous",
)
#: States in which provider work has actually left, or its outcome is unknown.
#: A newer human intent waits behind these; it is never refused because of them.
IN_FLIGHT_STATES = ("attempting", "ambiguous")

#: Bounded work per trigger. There is no daemon, worker, or poll: dispatch is
#: driven by an explicit human action, a sync, or app-start recovery.
MAX_PLANS_PER_TRIGGER = 10


class CalendarWriteError(ValueError):
    """A refusal that is about validity, never about provider availability."""


class CalendarWriteNotFound(CalendarWriteError):
    pass


class CalendarWriteRevisionConflict(CalendarWriteError):
    """The block changed under the human's feet; the renderer re-reads and retries.

    This is an Ion-local optimistic-concurrency check on a canonical revision.
    It is emphatically *not* a provider conflict and never reaches the owner as
    one.
    """


class CalendarWriteIneligible(CalendarWriteError):
    pass


@dataclass(frozen=True)
class _Target:
    """Provider authority derived server-side. Never renderer-supplied."""

    account_id: str
    calendar_id: str
    provider_event_id: str
    provider_etag: str | None
    block_revision: int


def _now() -> str:
    from ion_api.calendar import utc_now

    return utc_now()


class CalendarWriteCoordinator:
    def __init__(self, engine: Engine):
        self.engine = engine

    # --- Human lane -------------------------------------------------------

    def accept_direct_human_intent(
        self, block_id: str, input: DirectHumanIntentInput
    ) -> DirectHumanIntentReceipt:
        """Accept an authorized human action durably.

        Deliberately reads no provider lifecycle state. The only reasons this
        can fail are validity reasons -- an unknown block, a stale canonical
        revision, an ineligible provider target, or a value outside a closed
        vocabulary. "Provider busy" is not among them and cannot become one
        without changing this method's inputs.
        """

        if input.operation not in ACCEPTED_OPERATIONS:
            raise CalendarWriteVocabularyError("operation")
        if input.recurrence_scope not in ACCEPTED_RECURRENCE_SCOPES:
            raise CalendarWriteVocabularyError("recurrence_scope")
        unknown = set(input.changed_fields) - CHANGED_FIELDS
        if unknown:
            raise CalendarWriteVocabularyError("changed_fields")

        with self.engine.begin() as connection:
            target = self._resolve_target(connection, block_id, input.expected_revision)

            # The newest unresolved intent for this block, if any. A newer human
            # intent is accepted regardless; this only records the chain so R1
            # and R2 can implement supersession and coalescing without a schema
            # or contract change.
            predecessor = connection.execute(
                select(
                    calendar_provider_write_intents.c.id,
                    calendar_provider_write_intents.c.sequence,
                )
                .where(
                    and_(
                        calendar_provider_write_intents.c.calendar_block_id == block_id,
                        calendar_provider_write_intents.c.state.in_(UNRESOLVED_STATES),
                    )
                )
                .order_by(calendar_provider_write_intents.c.sequence.desc())
                .limit(1)
            ).one_or_none()

            highest = connection.execute(
                select(func.max(calendar_provider_write_intents.c.sequence)).where(
                    calendar_provider_write_intents.c.calendar_block_id == block_id
                )
            ).scalar()

            awaiting = predecessor is not None
            state = "queued" if awaiting else "ready"
            intent_id = str(uuid4())
            now = _now()
            connection.execute(
                insert(calendar_provider_write_intents).values(
                    id=intent_id,
                    command_id=input.command_id,
                    calendar_block_id=block_id,
                    account_id=target.account_id,
                    calendar_id=target.calendar_id,
                    provider_event_id=target.provider_event_id,
                    sequence=(highest or 0) + 1,
                    predecessor_intent_id=(
                        predecessor.id if predecessor is not None else None
                    ),
                    operation=input.operation,
                    recurrence_scope=input.recurrence_scope,
                    changed_fields_json=json.dumps(
                        sorted(input.changed_fields), separators=(",", ":")
                    ),
                    base_values_json=None,
                    desired_values_json=input.draft.model_dump_json(exclude_none=True),
                    expected_provider_etag=target.provider_etag,
                    source_block_revision=target.block_revision,
                    schema_version=1,
                    state=state,
                    attempt_count=0,
                    created_at=now,
                    updated_at=now,
                    provenance="direct_human",
                )
            )
            self._audit(
                connection,
                intent_id=intent_id,
                block_id=block_id,
                action=("write_intent_queued" if awaiting else "write_intent_ready"),
                operation=input.operation,
                changed_fields=sorted(input.changed_fields),
                attempt_count=0,
                from_state=None,
                to_state=state,
                source_revision=target.block_revision,
                executor_provenance="direct_human",
            )
            return DirectHumanIntentReceipt(
                intent_id=intent_id,
                block_id=block_id,
                sequence=(highest or 0) + 1,
                state=state,
                awaiting_predecessor=awaiting,
            )

    # --- Provider lane ----------------------------------------------------

    def select_provider_work(self, account_id: str | None = None) -> ProviderWorkOutput:
        """Read the durable authorized intents that provider work may act on.

        At most one plan per target, and none for a target whose earlier write
        is genuinely in flight: Ion never cancels an in-flight provider request
        and never races a parallel one against the same event.
        """

        with self.engine.begin() as connection:
            rows = connection.execute(
                select(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.state.in_(UNRESOLVED_STATES))
                .order_by(
                    calendar_provider_write_intents.c.created_at,
                    calendar_provider_write_intents.c.sequence,
                )
            ).all()

        busy_targets = {
            row.calendar_block_id for row in rows if row.state in IN_FLIGHT_STATES
        }
        plans: list[ProviderWritePlan] = []
        claimed: set[str] = set()
        for row in rows:
            if account_id is not None and row.account_id != account_id:
                continue
            if row.state != "ready":
                continue
            if row.calendar_block_id in busy_targets:
                continue
            if row.calendar_block_id in claimed:
                continue
            claimed.add(row.calendar_block_id)
            plans.append(
                ProviderWritePlan(
                    intent_id=row.id,
                    block_id=row.calendar_block_id,
                    account_id=row.account_id,
                    calendar_id=row.calendar_id,
                    provider_event_id=row.provider_event_id,
                    operation=row.operation,
                    recurrence_scope=row.recurrence_scope,
                    changed_fields=json.loads(row.changed_fields_json),
                    desired=DirectHumanEditDraft.model_validate_json(
                        row.desired_values_json or "{}"
                    ),
                    expected_provider_etag=row.expected_provider_etag,
                    attempt_count=row.attempt_count,
                    dispatchable=row.operation in DISPATCHABLE_OPERATIONS,
                )
            )
            if len(plans) >= MAX_PLANS_PER_TRIGGER:
                break
        return ProviderWorkOutput(plans=plans, provider_busy=bool(busy_targets))

    def begin_attempt(self, intent_id: str) -> None:
        with self.engine.begin() as connection:
            row = self._intent(connection, intent_id)
            if row.state != "ready":
                raise CalendarWriteError("intent is not ready")
            attempts = row.attempt_count + 1
            now = _now()
            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == intent_id)
                .values(
                    state="attempting",
                    attempt_count=attempts,
                    last_attempt_at=now,
                    next_attempt_at=None,
                    updated_at=now,
                )
            )
            self._audit(
                connection,
                intent_id=intent_id,
                block_id=row.calendar_block_id,
                action="write_attempt_started",
                operation=row.operation,
                changed_fields=json.loads(row.changed_fields_json),
                attempt_count=attempts,
                from_state=row.state,
                to_state="attempting",
                source_revision=row.source_block_revision,
                executor_provenance="direct_human",
            )

    def record_outcome(
        self, intent_id: str, failure_class: str, safe_reason: str | None = None
    ) -> str | None:
        """Settle one provider attempt and classify it into the closed taxonomy.

        Returns the recovery kind, or ``None`` on success. Ordinary provider
        version drift classifies as automatic and re-arms for another bounded
        attempt: it is never escalated, and no state this method can reach is a
        generic disagreement handed to the owner.
        """

        recovery = None
        with self.engine.begin() as connection:
            row = self._intent(connection, intent_id)
            if row.state not in ("attempting", "ambiguous"):
                raise CalendarWriteError("intent has no attempt to settle")
            recovery = classify_failure(failure_class, row.attempt_count)
            now = _now()
            if recovery is None:
                state, action = "completed", "write_completed"
            elif failure_class == "reauthentication_required":
                state, action = "reauth_required", "write_reauthentication_required"
            elif is_automatically_recoverable(recovery):
                state, action = "retry_wait", "write_retry_scheduled"
            else:
                state, action = "failed", "write_failed_terminally"
            assert state not in COORDINATOR_UNUSED_STATES
            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == intent_id)
                .values(
                    state=state,
                    failure_class=None if recovery is None else failure_class,
                    failure_reason=safe_reason,
                    # A retry needs a due time; 0007 enforces that with a CHECK.
                    next_attempt_at=now if state == "retry_wait" else None,
                    resolved_at=now if state in ("completed", "failed") else None,
                    updated_at=now,
                )
            )
            self._audit(
                connection,
                intent_id=intent_id,
                block_id=row.calendar_block_id,
                action=action,
                operation=row.operation,
                changed_fields=json.loads(row.changed_fields_json),
                attempt_count=row.attempt_count,
                safe_reason_class=None if recovery is None else failure_class,
                safe_reason=safe_reason,
                from_state=row.state,
                to_state=state,
                source_revision=row.source_block_revision,
                executor_provenance="direct_human",
            )
            if state == "completed":
                self._release_successor(connection, row.calendar_block_id)
        return recovery

    def recover(self) -> RecoveryOutput:
        """Bounded, restart-safe recovery. No timer, no poll, no worker.

        An attempt persisted as `attempting` cannot have survived a restart, so
        its true outcome is unknown: it is repaired to `ambiguous` before any
        future dispatch selection, never silently retried.
        """

        repaired = 0
        with self.engine.begin() as connection:
            in_flight = connection.execute(
                select(calendar_provider_write_intents).where(
                    calendar_provider_write_intents.c.state == "attempting"
                )
            ).all()
            for row in in_flight:
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == row.id)
                    .values(state="ambiguous", updated_at=_now())
                )
                self._audit(
                    connection,
                    intent_id=row.id,
                    block_id=row.calendar_block_id,
                    action="write_outcome_ambiguous",
                    operation=row.operation,
                    changed_fields=json.loads(row.changed_fields_json),
                    attempt_count=row.attempt_count,
                    from_state="attempting",
                    to_state="ambiguous",
                    source_revision=row.source_block_revision,
                    executor_provenance="recovery",
                )
                repaired += 1

            # A waiting retry becomes ready again. R1 adds the single bounded
            # self-wake that makes this happen without another trigger.
            connection.execute(
                update(calendar_provider_write_intents)
                .where(
                    and_(
                        calendar_provider_write_intents.c.state == "retry_wait",
                        calendar_provider_write_intents.c.attempt_count < MAX_ATTEMPTS,
                    )
                )
                .values(state="ready", updated_at=_now())
            )

            rows = connection.execute(
                select(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.state.in_(UNRESOLVED_STATES))
                .order_by(calendar_provider_write_intents.c.created_at)
            ).all()
            failed = connection.execute(
                select(calendar_provider_write_intents).where(
                    calendar_provider_write_intents.c.state.in_(
                        ("failed", "reauth_required")
                    )
                )
            ).all()

        entries = []
        for row in list(rows) + list(failed):
            recovery = (
                classify_failure(row.failure_class, row.attempt_count)
                if row.failure_class
                else None
            )
            entries.append(
                RecoveryEntry(
                    intent_id=row.id,
                    block_id=row.calendar_block_id,
                    state=row.state,
                    recovery=recovery,
                    automatic=is_automatically_recoverable(recovery),
                    owner_action=requires_owner_action(recovery),
                )
            )
        return RecoveryOutput(entries=entries, repaired_in_flight=repaired)

    # --- internals --------------------------------------------------------

    def _release_successor(self, connection, block_id: str) -> None:
        waiting = connection.execute(
            select(calendar_provider_write_intents)
            .where(
                and_(
                    calendar_provider_write_intents.c.calendar_block_id == block_id,
                    calendar_provider_write_intents.c.state == "queued",
                )
            )
            .order_by(calendar_provider_write_intents.c.sequence)
            .limit(1)
        ).one_or_none()
        if waiting is None:
            return
        connection.execute(
            update(calendar_provider_write_intents)
            .where(calendar_provider_write_intents.c.id == waiting.id)
            .values(state="ready", updated_at=_now())
        )
        self._audit(
            connection,
            intent_id=waiting.id,
            block_id=block_id,
            action="write_intent_ready",
            operation=waiting.operation,
            changed_fields=json.loads(waiting.changed_fields_json),
            attempt_count=waiting.attempt_count,
            from_state="queued",
            to_state="ready",
            source_revision=waiting.source_block_revision,
            executor_provenance="recovery",
        )

    def _intent(self, connection, intent_id: str):
        row = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.id == intent_id
            )
        ).one_or_none()
        if row is None:
            raise CalendarWriteNotFound(intent_id)
        return row

    def _resolve_target(self, connection, block_id: str, expected_revision: int):
        block = connection.execute(
            select(calendar_blocks).where(calendar_blocks.c.id == block_id)
        ).one_or_none()
        if block is None:
            raise CalendarWriteNotFound(block_id)
        if block.revision != expected_revision:
            raise CalendarWriteRevisionConflict(block_id)
        link = connection.execute(
            select(google_event_links).where(
                google_event_links.c.calendar_block_id == block_id
            )
        ).one_or_none()
        if link is None:
            raise CalendarWriteIneligible("no confirmed provider link")
        if link.link_state != "confirmed":
            raise CalendarWriteIneligible("link is not confirmed")
        if link.provider_locked or link.has_attendees:
            raise CalendarWriteIneligible("provider target is not writable")
        if link.provider_event_type != "default":
            raise CalendarWriteIneligible("not an ordinary event")
        calendar = connection.execute(
            select(google_calendars).where(google_calendars.c.id == link.calendar_id)
        ).one_or_none()
        if calendar is None or calendar.access_role not in ("writer", "owner"):
            raise CalendarWriteIneligible("calendar is not writable")
        account = connection.execute(
            select(google_accounts).where(google_accounts.c.id == link.account_id)
        ).one_or_none()
        if account is None or account.calendar_write_scope_state != "write_granted":
            raise CalendarWriteIneligible("account has not granted write access")
        return _Target(
            account_id=link.account_id,
            calendar_id=link.calendar_id,
            provider_event_id=link.provider_event_id,
            provider_etag=link.provider_etag,
            block_revision=block.revision,
        )

    def _audit(
        self,
        connection,
        *,
        intent_id: str,
        block_id: str,
        action: str,
        operation: str,
        changed_fields: list[str],
        attempt_count: int,
        from_state: str | None,
        to_state: str,
        source_revision: int | None,
        executor_provenance: str,
        safe_reason_class: str | None = None,
        safe_reason: str | None = None,
    ) -> None:
        connection.execute(
            insert(calendar_provider_write_audit).values(
                id=str(uuid4()),
                intent_id=intent_id,
                calendar_block_id=block_id,
                action=action,
                operation=operation,
                changed_fields_json=json.dumps(changed_fields, separators=(",", ":")),
                attempt_count=attempt_count,
                safe_reason_class=safe_reason_class,
                safe_reason=safe_reason,
                from_state=from_state,
                to_state=to_state,
                source_revision=source_revision,
                resulting_revision=None,
                occurred_at=_now(),
                executor_provenance=executor_provenance,
            )
        )
