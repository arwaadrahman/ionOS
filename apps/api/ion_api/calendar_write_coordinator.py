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
    ConfirmedProviderEvent,
    DirectHumanEditDraft,
    DirectHumanIntentInput,
    DirectHumanIntentReceipt,
    ProviderOutcomeResult,
    ProviderWorkOutput,
    ProviderWritePlan,
    RecoveryEntry,
    RecoveryOutput,
    WriteConsentOutput,
)
from ion_api.calendar_write_model import (
    ACCEPTED_OPERATIONS,
    ACCEPTED_RECURRENCE_SCOPES,
    AUTOMATIC_RECOVERY,
    CAPABILITY_RECOVERY,
    CHANGED_FIELDS,
    COORDINATOR_UNUSED_STATES,
    DISPATCHABLE_OPERATIONS,
    MAX_ATTEMPTS,
    OWNER_ACTION_RECOVERY,
    CalendarWriteVocabularyError,
    classify_capability,
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
#: An earlier write that has not actually left yet. A newer human edit for the
#: same target supersedes these, so an obsolete value costs no provider
#: round-trip. Nothing here has been sent, so nothing is cancelled mid-flight.
SUPERSEDABLE_STATES = ("queued", "ready", "retry_wait")
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
    base_values: dict
    #: Set when the account cannot currently be written to. The intent is still
    #: accepted durably; it simply waits for the one-time capability grant.
    capability_recovery: str | None = None


def _temporal(row, edge: str) -> dict | None:
    """The confirmed base value for one temporal edge, in provider shape."""

    if row.temporal_kind == "all_day":
        value = getattr(row, f"{edge}_date")
        return None if value is None else {"date": value}
    instant = getattr(row, f"{edge}_at")
    if instant is None:
        return None
    return {
        "date_time": instant,
        "time_zone": getattr(row, f"{edge}_timezone") or "UTC",
    }


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
                select(calendar_provider_write_intents)
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

            # Supersede an earlier write that has not actually left yet: the
            # owner's newest value is the only one worth sending. A write that
            # is genuinely in flight is never cancelled and never raced -- the
            # newer intent waits durably behind it instead.
            superseded = None
            if predecessor is not None and predecessor.state in SUPERSEDABLE_STATES:
                superseded = predecessor.id
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == predecessor.id)
                    .values(
                        state="cancelled",
                        resolved_at=_now(),
                        updated_at=_now(),
                        failure_reason="superseded_by_newer_human_intent",
                    )
                )
                self._audit(
                    connection,
                    intent_id=predecessor.id,
                    block_id=block_id,
                    action="write_cancelled",
                    operation=input.operation,
                    changed_fields=json.loads(predecessor.changed_fields_json),
                    attempt_count=predecessor.attempt_count,
                    from_state=predecessor.state,
                    to_state="cancelled",
                    source_revision=target.block_revision,
                    executor_provenance="direct_human",
                )

            blocked_by_predecessor = superseded is None and predecessor is not None
            awaiting = blocked_by_predecessor or target.capability_recovery is not None
            if target.capability_recovery is not None:
                state = "reauth_required"
            elif blocked_by_predecessor:
                state = "queued"
            else:
                state = "ready"
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
                    base_values_json=json.dumps(
                        {
                            field: target.base_values[field]
                            for field in sorted(input.changed_fields)
                        },
                        separators=(",", ":"),
                    ),
                    desired_values_json=input.draft.model_dump_json(exclude_none=True),
                    expected_provider_etag=target.provider_etag,
                    source_block_revision=target.block_revision,
                    schema_version=1,
                    state=state,
                    attempt_count=0,
                    failure_class=(
                        "reauthentication_required"
                        if target.capability_recovery is not None
                        else None
                    ),
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
                superseded_intent_id=superseded,
                requires_write_consent=target.capability_recovery,
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
            if row.operation not in DISPATCHABLE_OPERATIONS:
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
        self,
        intent_id: str,
        failure_class: str,
        safe_reason: str | None = None,
        confirmed: ConfirmedProviderEvent | None = None,
    ) -> ProviderOutcomeResult:
        """Settle one provider attempt.

        Ordinary provider version drift is resolved *here*, automatically. It is
        not a disagreement about facts and never becomes a decision handed to
        the owner: Ion adopts the freshly confirmed authority, keeps the fields
        the human actually changed, and re-aims the same intent.
        """

        with self.engine.begin() as connection:
            row = self._intent(connection, intent_id)
            if row.state not in ("attempting", "ambiguous"):
                raise CalendarWriteError("intent has no attempt to settle")
            recovery = classify_failure(failure_class, row.attempt_count)
            now = _now()
            rebased = False

            if recovery is None:
                state, action = "completed", "write_completed"
                self._settle_confirmed(connection, row, confirmed)
            elif recovery == "provider_version_drift" and confirmed is not None:
                # Automatic ETag rebase. Structural identity is re-proved before
                # re-aiming; a *version* difference is never an identity failure.
                structural = self._structural_failure(confirmed)
                if structural is not None:
                    recovery, failure_class = structural
                    safe_reason = recovery
                    state, action = "failed", "write_failed_terminally"
                else:
                    rebased = True
                    state, action = "ready", "write_retry_scheduled"
                    self._rebase(connection, row, confirmed)
            elif failure_class == "reauthentication_required":
                state, action = "reauth_required", "write_reauthentication_required"
            elif is_automatically_recoverable(recovery):
                state, action = "retry_wait", "write_retry_scheduled"
            else:
                state, action = "failed", "write_failed_terminally"

            assert state not in COORDINATOR_UNUSED_STATES
            values = {
                "state": state,
                "failure_class": None if recovery is None else failure_class,
                "failure_reason": safe_reason,
                "next_attempt_at": now if state == "retry_wait" else None,
                "resolved_at": now if state in ("completed", "failed") else None,
                "updated_at": now,
            }
            if rebased and confirmed is not None:
                values["expected_provider_etag"] = confirmed.provider_etag
                values["base_values_json"] = self._rebased_base(row, confirmed)
                values["failure_class"] = None
                values["failure_reason"] = None
            connection.execute(
                update(calendar_provider_write_intents)
                .where(calendar_provider_write_intents.c.id == intent_id)
                .values(**values)
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
                executor_provenance="recovery" if rebased else "direct_human",
            )
            if state in ("completed", "failed"):
                self._release_successor(connection, row.calendar_block_id, confirmed)
        return ProviderOutcomeResult(
            recovery=None if rebased else recovery, state=state, rebased=rebased
        )

    @staticmethod
    def _structural_failure(
        confirmed: ConfirmedProviderEvent,
    ) -> tuple[str, str] | None:
        """A real contradiction, as opposed to ordinary version drift.

        Structural identity -- same target, still ordinary, still writable -- is
        what may legitimately fail during a rebase. A *version* difference is
        not, and treating one as the other is the exact defect that produced a
        permanent review loop in Phase 2C v1.

        Returns the closed-taxonomy recovery kind and the storage failure class
        it is recorded under. 0007's failure_class vocabulary is coarser than
        the product taxonomy and cannot be widened without a migration, so the
        precise kind is carried in `failure_reason` -- which the coordinator
        only ever writes closed-set values into.
        """

        if confirmed.deleted:
            return "provider_target_deleted", "provider_not_found"
        if confirmed.recurring:
            return "recurrence_identity_lost", "invalid_target"
        if (
            confirmed.has_attendees
            or confirmed.provider_locked
            or confirmed.event_type != "default"
        ):
            return "unsupported_provider_transformation", "invalid_target"
        return None

    @staticmethod
    def _rebased_base(row, confirmed: ConfirmedProviderEvent) -> str:
        """Adopt Google's latest values for the fields the human did not touch.

        The pending intent keeps its own changed fields, so Google's edits to
        other fields survive and the human's edit is not silently discarded.
        This is field ownership falling out of the narrow model, not a merge
        rule and not last-write-wins.
        """

        changed = set(json.loads(row.changed_fields_json))
        base = json.loads(row.base_values_json or "{}")
        latest = {
            "title": confirmed.title,
            "start": (
                confirmed.start.model_dump(exclude_none=True)
                if confirmed.start
                else None
            ),
            "end": (
                confirmed.end.model_dump(exclude_none=True) if confirmed.end else None
            ),
        }
        for field in changed:
            if latest.get(field) is not None:
                base[field] = latest[field]
        return json.dumps(base, separators=(",", ":"))

    def _rebase(self, connection, row, confirmed: ConfirmedProviderEvent) -> None:
        """Align the confirmed provider link with freshly observed authority."""

        connection.execute(
            update(google_event_links)
            .where(google_event_links.c.calendar_block_id == row.calendar_block_id)
            .values(provider_etag=confirmed.provider_etag)
        )

    def _settle_confirmed(
        self, connection, row, confirmed: ConfirmedProviderEvent | None
    ) -> None:
        """Promote a confirmed provider result into canonical state.

        An older confirmation must never displace a newer human intent, so the
        canonical block is only updated for fields no *later* unresolved intent
        still owns. The newer intent keeps projecting its own value until it
        settles in turn, and the display never flicks back through a superseded
        value.
        """

        if confirmed is None:
            return
        connection.execute(
            update(google_event_links)
            .where(google_event_links.c.calendar_block_id == row.calendar_block_id)
            .values(provider_etag=confirmed.provider_etag)
        )
        newer = connection.execute(
            select(calendar_provider_write_intents.c.changed_fields_json).where(
                and_(
                    calendar_provider_write_intents.c.calendar_block_id
                    == row.calendar_block_id,
                    calendar_provider_write_intents.c.sequence > row.sequence,
                    calendar_provider_write_intents.c.state.in_(UNRESOLVED_STATES),
                )
            )
        ).all()
        owned_by_newer: set[str] = set()
        for entry in newer:
            owned_by_newer.update(json.loads(entry.changed_fields_json))

        desired = json.loads(row.desired_values_json or "{}")
        values: dict = {}
        for field in json.loads(row.changed_fields_json):
            if field in owned_by_newer or field not in desired:
                continue
            if field == "title":
                values["title"] = desired["title"]
            else:
                value = desired[field]
                if "date" in value:
                    values[f"{field}_date"] = value["date"]
                    values[f"{field}_at"] = None
                else:
                    values[f"{field}_at"] = value["date_time"]
                    values[f"{field}_timezone"] = value["time_zone"]
                    values[f"{field}_date"] = None
        if values:
            values["updated_at"] = _now()
            connection.execute(
                update(calendar_blocks)
                .where(calendar_blocks.c.id == row.calendar_block_id)
                .values(**values)
            )

    def grant_write_capability(self, account_id: str) -> WriteConsentOutput:
        """Record the one-time write capability grant and resume waiting edits.

        The owner never retypes an edit they already made: intents parked on the
        missing capability become dispatchable again here.
        """

        resumed: list[str] = []
        with self.engine.begin() as connection:
            account = connection.execute(
                select(google_accounts).where(google_accounts.c.id == account_id)
            ).one_or_none()
            if account is None:
                raise CalendarWriteNotFound(account_id)
            connection.execute(
                update(google_accounts)
                .where(google_accounts.c.id == account_id)
                .values(calendar_write_scope_state="write_granted", updated_at=_now())
            )
            waiting = connection.execute(
                select(calendar_provider_write_intents)
                .where(
                    and_(
                        calendar_provider_write_intents.c.account_id == account_id,
                        calendar_provider_write_intents.c.state == "reauth_required",
                    )
                )
                .order_by(calendar_provider_write_intents.c.sequence)
            ).all()
            for row in waiting:
                connection.execute(
                    update(calendar_provider_write_intents)
                    .where(calendar_provider_write_intents.c.id == row.id)
                    .values(
                        state="ready",
                        failure_class=None,
                        failure_reason=None,
                        updated_at=_now(),
                    )
                )
                self._audit(
                    connection,
                    intent_id=row.id,
                    block_id=row.calendar_block_id,
                    action="write_intent_ready",
                    operation=row.operation,
                    changed_fields=json.loads(row.changed_fields_json),
                    attempt_count=row.attempt_count,
                    from_state="reauth_required",
                    to_state="ready",
                    source_revision=row.source_block_revision,
                    executor_provenance="recovery",
                )
                resumed.append(row.id)
        return WriteConsentOutput(account_id=account_id, resumed_intent_ids=resumed)

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

        with self.engine.connect() as connection:
            scopes = {
                account.id: account.calendar_write_scope_state
                for account in connection.execute(select(google_accounts))
            }

        entries = []
        for row in list(rows) + list(failed):
            recovery = recovery_kind_for(row, scopes.get(row.account_id, "read_only"))
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

    def _release_successor(self, connection, block_id: str, confirmed=None) -> None:
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
        released = {"state": "ready", "updated_at": _now()}
        if confirmed is not None:
            # Re-aim the waiting intent at the authority the attempt just
            # confirmed, so it dispatches against a fresh ETag rather than
            # meeting a precondition it already knows is stale.
            released["expected_provider_etag"] = confirmed.provider_etag
            released["base_values_json"] = self._rebased_base(waiting, confirmed)
        connection.execute(
            update(calendar_provider_write_intents)
            .where(calendar_provider_write_intents.c.id == waiting.id)
            .values(**released)
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
        if account is None:
            raise CalendarWriteNotFound(link.account_id)
        # Missing write permission is deliberately *not* a refusal. The owner's
        # edit is authorized and becomes durable; what is missing is an account
        # capability they grant once. Refusing here would make them retype the
        # edit after consenting, which is the behaviour the contract forbids.
        capability = classify_capability(account.calendar_write_scope_state)
        return _Target(
            account_id=link.account_id,
            calendar_id=link.calendar_id,
            provider_event_id=link.provider_event_id,
            provider_etag=link.provider_etag,
            block_revision=block.revision,
            base_values={
                "title": block.title,
                "start": _temporal(block, "start"),
                "end": _temporal(block, "end"),
            },
            capability_recovery=capability,
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


def recovery_kind_for(row, scope_state: str) -> str | None:
    """The precise closed-taxonomy recovery kind for one stored intent.

    `failure_class` is 0007's coarser storage vocabulary; when the coordinator
    recorded a more precise member of the closed taxonomy it lives in
    `failure_reason`. Anything outside the taxonomy is ignored rather than
    passed through, so an unknown string can never reach the owner as a state.
    """

    if not row.failure_class:
        return None
    kind = classify_failure(row.failure_class, row.attempt_count)
    precise = row.failure_reason
    if precise in AUTOMATIC_RECOVERY or precise in OWNER_ACTION_RECOVERY:
        kind = precise
    if kind in CAPABILITY_RECOVERY:
        # Never granted and granted-then-lost are different situations with
        # different truthful copy; only the first is a capability transition.
        kind = classify_capability(scope_state)
    return kind


def pending_human_overlay(connection) -> tuple[dict[str, dict], list[dict]]:
    """The newest durable human intent per block, plus owner-action recovery.

    Visible Calendar state is *confirmed provider base + newest durable human
    changed fields*. This computes the second half. It returns only values, and
    deliberately no lifecycle state: an ordinary Calendar event must never carry
    "pending", "syncing", or "Not saved yet".

    The recovery list is separate and top-level for the same reason. It holds
    only conditions the owner must actually settle, each named specifically, and
    is empty in healthy operation.
    """

    rows = connection.execute(
        select(calendar_provider_write_intents)
        .where(calendar_provider_write_intents.c.state.in_(UNRESOLVED_STATES))
        .order_by(
            calendar_provider_write_intents.c.calendar_block_id,
            calendar_provider_write_intents.c.sequence,
        )
    ).all()
    failures = connection.execute(
        select(calendar_provider_write_intents).where(
            calendar_provider_write_intents.c.state.in_(("failed", "reauth_required"))
        )
    ).all()
    scopes = {
        account.id: account.calendar_write_scope_state
        for account in connection.execute(select(google_accounts))
    }

    overlay: dict[str, dict] = {}
    for row in rows:
        # Later sequence wins the fields it changed, so the newest human intent
        # is what the owner sees and an older one never displaces it.
        desired = json.loads(row.desired_values_json or "{}")
        block = overlay.setdefault(row.calendar_block_id, {})
        for field in json.loads(row.changed_fields_json):
            if field in desired:
                block[field] = desired[field]

    recovery: list[dict] = []
    for row in failures:
        kind = recovery_kind_for(row, scopes.get(row.account_id, "read_only"))
        if kind is None or not requires_owner_action(kind):
            continue
        recovery.append(
            {
                "block_id": row.calendar_block_id,
                "account_id": row.account_id,
                "kind": kind,
            }
        )
    return overlay, recovery


def pending_changed_fields(connection, block_id: str) -> set[str]:
    """Fields a durable human intent currently owns for this block.

    A background read sync must not overwrite these, and must never turn the
    difference into a review state: while the intent is unsettled the human owns
    exactly the fields they changed, and Google owns every other field.
    """

    rows = connection.execute(
        select(calendar_provider_write_intents.c.changed_fields_json).where(
            and_(
                calendar_provider_write_intents.c.calendar_block_id == block_id,
                calendar_provider_write_intents.c.state.in_(UNRESOLVED_STATES),
            )
        )
    ).all()
    owned: set[str] = set()
    for row in rows:
        owned.update(json.loads(row.changed_fields_json))
    return owned
