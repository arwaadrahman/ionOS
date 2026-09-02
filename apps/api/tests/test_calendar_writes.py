import json
import re
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import func, insert, select, update
from test_migrations import migration_config

from ion_api.calendar import (
    CalendarConflictError,
    CalendarService,
    CalendarValidationError,
)
from ion_api.calendar_contracts import (
    CALENDAR_LIST_SCOPE,
    EVENTS_READ_SCOPE,
    EVENTS_WRITE_SCOPE,
    CalendarCategoryInput,
    GoogleAccountConnectInput,
    ProviderCalendarInput,
    ProviderDateTime,
    ProviderEventInput,
    SyncBeginInput,
    SyncCompleteInput,
    SyncPageInput,
)
from ion_api.calendar_write_contracts import (
    ApplyIonChangesInput,
    BeginWriteAttemptInput,
    CreateProviderEventInput,
    DeleteProviderEventInput,
    EditProviderEventInput,
    KeepGoogleVersionInput,
    ProviderWriteValues,
    PruneWriteIntentsInput,
    QueueProviderWriteIntentInput,
    ReadyWriteIntentsInput,
    ReconcileProviderCreateInput,
    ReconcileProviderDeleteInput,
    ReconcileProviderPatchInput,
    RecordProviderWriteResultInput,
    RecoverWriteIntentsInput,
    ResolveProviderOccurrenceInput,
    WriteIntentTransitionInput,
)
from ion_api.calendar_writes import (
    MAX_AUTOMATIC_ATTEMPTS,
    CalendarWriteService,
    deterministic_google_event_id,
    full_jitter_delay_seconds,
)
from ion_api.db import create_database_engine
from ion_api.main import create_production_app
from ion_api.migrations import upgrade_to_head
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
from ion_api.settings import Settings


def _connected(tmp_path, *, write=True, access_role="owner", event_overrides=None):
    database_path = tmp_path / f"writes-{uuid4()}.sqlite3"
    command.upgrade(migration_config(database_path), "head")
    engine = create_database_engine(database_path)
    calendar = CalendarService(engine)
    scopes = [
        CALENDAR_LIST_SCOPE,
        EVENTS_WRITE_SCOPE if write else EVENTS_READ_SCOPE,
    ]
    status = calendar.connect_account(
        GoogleAccountConnectInput(
            provider_account_id=f"synthetic-{uuid4()}@example.invalid",
            display_name="Synthetic Calendar Account",
            granted_scopes=scopes,
            keychain_locator=f"synthetic-locator-{uuid4()}",
            calendars=[
                ProviderCalendarInput(
                    provider_calendar_id="synthetic-calendar@example.invalid",
                    summary="Synthetic calendar",
                    timezone="America/Los_Angeles",
                    access_role=access_role,
                    is_primary=True,
                    provider_selected=True,
                )
            ],
        )
    )
    calendar_id = status.calendars[0].id
    generation = str(uuid4())
    calendar.begin_sync(calendar_id, SyncBeginInput(generation=generation, mode="full"))
    values = {
        "provider_event_id": "synthetic-provider-event",
        "provider_etag": '"synthetic-etag"',
        "title": "Synthetic event title",
        "start": ProviderDateTime(
            date_time="2030-01-01T09:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
        "end": ProviderDateTime(
            date_time="2030-01-01T10:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
    }
    values.update(event_overrides or {})
    calendar.apply_sync_page(
        calendar_id,
        SyncPageInput(
            generation=generation,
            events=[ProviderEventInput(**values)],
        ),
    )
    calendar.complete_sync(
        calendar_id,
        SyncCompleteInput(generation=generation, next_sync_token="synthetic-sync"),
    )
    block = calendar.status().blocks[0]
    return engine, calendar, CalendarWriteService(engine), block


def _queue(writes, block, *, command_id=None):
    return writes.queue(
        QueueProviderWriteIntentInput(
            command_id=command_id or str(uuid4()),
            calendar_block_id=block.id,
            operation="patch",
            recurrence_scope="single",
            changed_fields=["title"],
            base_values=ProviderWriteValues(title="Synthetic event title"),
            desired_values=ProviderWriteValues(title="Synthetic revised title"),
            expected_block_revision=block.revision,
        )
    )


def _transition(writes, intent, target, *, result=None, next_attempt_at=None):
    return writes.transition(
        intent.id,
        WriteIntentTransitionInput(
            expected_state=intent.state,
            target_state=target,
            occurred_at="2030-01-01T12:00:00Z",
            executor_provenance="recovery",
            result_class=result,
            next_attempt_at=next_attempt_at,
        ),
    )


def _exhaust_to_conflict(writes, intent):
    """Drive an intent past the automatic rebase budget into a real conflict.

    Ordinary ETag drift now rebases and retries automatically, so a conflict is
    only reachable once the bounded attempt budget is spent. Tests that need a
    conflict must earn one the way production does.
    """
    current = intent
    for _ in range(MAX_AUTOMATIC_ATTEMPTS + 2):
        if current.state == "conflict":
            return current
        if current.state != "attempting":
            try:
                current = writes.begin_attempt(
                    current.id,
                    BeginWriteAttemptInput(
                        expected_state=current.state,
                        executor_provenance="direct_human",
                    ),
                )
            except CalendarConflictError:
                # The caller handed us a summary taken before its own
                # begin_attempt; the row is already mid-attempt.
                pass
        current = writes.record_result(
            current.id,
            RecordProviderWriteResultInput(
                stage="patch",
                result_class="stale_precondition",
                safe_reason="synthetic_safe_reason",
            ),
        )
    raise AssertionError(f"intent never reached conflict: {current.state}")


def _create(writes, calendar, *, command_id=None, **overrides):
    values = {
        "command_id": command_id or str(uuid4()),
        "calendar_id": calendar.status().calendars[0].id,
        "title": "Synthetic owner-created event",
        "date": "2030-01-02",
        "all_day": False,
        "start_time": "09:00",
        "end_time": "10:00",
        "timezone": "America/Los_Angeles",
    }
    values.update(overrides)
    return writes.create(CreateProviderEventInput(**values))


def _edit(writes, block, *, command_id=None, **overrides):
    values = {
        "command_id": command_id or str(uuid4()),
        "calendar_block_id": block.id,
        "edit_kind": "edit",
        "expected_block_revision": block.revision,
        "title": "Synthetic revised title",
        "locked_confirmed": True,
    }
    values.update(overrides)
    return writes.edit(EditProviderEventInput(**values))


def _delete(writes, block, *, command_id=None, **overrides):
    values = {
        "command_id": command_id or str(uuid4()),
        "calendar_block_id": block.id,
        "expected_block_revision": block.revision,
        "locked_confirmed": True,
    }
    values.update(overrides)
    return writes.delete(DeleteProviderEventInput(**values))


def test_delete_is_local_first_etag_bound_and_audited(tmp_path):
    engine, calendar, writes, block = _connected(tmp_path)
    command_id = str(uuid4())
    intent = _delete(writes, block, command_id=command_id)
    assert intent.operation == "delete_event"
    assert intent.state == "ready"
    projected = calendar.status().blocks[0]
    assert projected.status == "confirmed"
    assert projected.provider_write_operation == "delete_event"
    assert projected.provider_write_state == "pending"
    plan = writes.ready(ReadyWriteIntentsInput())[0]
    assert plan.expected_provider_etag == '"synthetic-etag"'
    assert plan.changed_fields == ["status"]
    assert plan.desired_values.status == "cancelled"
    with engine.connect() as connection:
        actions = (
            connection.execute(
                select(audit_events.c.action).where(
                    audit_events.c.command_id == command_id
                )
            )
            .scalars()
            .all()
        )
    assert actions == ["delete_requested"]


def test_never_attempted_create_cancels_locally_without_delete_intent(tmp_path):
    engine, calendar, writes, _ = _connected(tmp_path)
    created = _create(writes, calendar)
    pending = next(
        item
        for item in calendar.status().blocks
        if item.id == created.calendar_block_id
    )
    assert pending.provider_delete_capability.mode == "local_create_cancel"
    command_id = str(uuid4())
    assert _delete(writes, pending, command_id=command_id) is None
    assert _delete(writes, pending, command_id=command_id) is None
    with engine.connect() as connection:
        operations = (
            connection.execute(
                select(calendar_provider_write_intents.c.operation).where(
                    calendar_provider_write_intents.c.calendar_block_id == pending.id
                )
            )
            .scalars()
            .all()
        )
    assert operations == ["create"]
    cancelled = next(item for item in calendar.status().blocks if item.id == pending.id)
    assert cancelled.status == "cancelled"
    assert cancelled.provider_deleted_at is not None


def test_attempted_create_requires_reconciliation_before_delete(tmp_path):
    _, calendar, writes, _ = _connected(tmp_path)
    created = _create(writes, calendar)
    writes.begin_attempt(
        created.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    pending = next(
        item
        for item in calendar.status().blocks
        if item.id == created.calendar_block_id
    )
    assert pending.provider_delete_capability.reason == "create_reconciliation_required"
    with pytest.raises(CalendarValidationError, match="create_reconciliation_required"):
        _delete(writes, pending)


def test_delete_404_completes_and_ambiguous_live_target_retries(tmp_path):
    _, calendar, writes, block = _connected(tmp_path)
    intent = _delete(writes, block)
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    completed = writes.reconcile_delete(
        intent.id,
        ReconcileProviderDeleteInput(resolution_kind="already_absent"),
    )
    assert completed.state == "completed"
    assert completed.failure_reason == "provider_already_absent"
    assert calendar.status().blocks[0].status == "cancelled"

    _, _, writes2, block2 = _connected(tmp_path)
    intent2 = _delete(writes2, block2)
    writes2.begin_attempt(
        intent2.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    ambiguous = writes2.record_result(
        intent2.id,
        RecordProviderWriteResultInput(
            stage="delete",
            result_class="retryable_transport",
            safe_reason="transport_failure",
        ),
    )
    writes2.begin_attempt(
        intent2.id,
        BeginWriteAttemptInput(
            expected_state="ambiguous", executor_provenance="recovery"
        ),
    )
    retry = writes2.reconcile_delete(
        intent2.id,
        ReconcileProviderDeleteInput(
            resolution_kind="identity_lookup",
            event=ProviderEventInput(
                provider_event_id=block2.provider_event_id,
                provider_etag='"synthetic-etag"',
                title="Synthetic event title",
                start=ProviderDateTime(
                    date_time="2030-01-01T09:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
                end=ProviderDateTime(
                    date_time="2030-01-01T10:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
            ),
        ),
    )
    assert ambiguous.state == "ambiguous"
    assert retry.state == "retry_wait"


def test_keep_google_version_discards_intent_and_preserves_ion_metadata(tmp_path):
    engine, calendar, writes, block = _connected(tmp_path)
    calendar.set_category(
        block.id,
        CalendarCategoryInput(
            category="personal", category_subtype="errand", expected_revision=1
        ),
    )
    intent = _edit(writes, block, title="Renamed while offline")
    conflicted = _exhaust_to_conflict(writes, intent)
    assert conflicted.state == "conflict"

    before = next(item for item in calendar.status().blocks if item.id == block.id)
    assert before.provider_write_state == "conflict"
    # The state is reported truthfully, but the owner is never locked out of
    # their own event: acting again supersedes the pending intent.
    assert before.provider_write_capability.eligible is True

    kept = writes.keep_google_version(
        KeepGoogleVersionInput(
            command_id=str(uuid4()),
            calendar_block_id=block.id,
            expected_block_revision=before.revision,
        )
    )
    assert kept.state == "cancelled"

    after = next(item for item in calendar.status().blocks if item.id == block.id)
    # The confirmed Google title (never overwritten) is visible again, and
    # the block is editable -- the conflict is genuinely cleared.
    assert after.title == "Synthetic event title"
    assert after.provider_write_state == "synced"
    assert after.provider_write_capability.eligible is True
    # Ion-only metadata is untouched by a provider-field resolution.
    assert after.category == "personal"
    assert after.category_subtype == "errand"
    assert after.ion_metadata_revision == 2

    # No unrelated CalendarBlock or intent was touched.
    with engine.connect() as connection:
        remaining_intents = (
            connection.execute(
                select(calendar_provider_write_intents.c.id).where(
                    calendar_provider_write_intents.c.calendar_block_id == block.id
                )
            )
            .scalars()
            .all()
        )
    assert remaining_intents == [intent.id]

    # A repeat Keep Google call has nothing left to resolve -- it does not
    # silently re-cancel or duplicate audit evidence.
    with pytest.raises(CalendarValidationError, match="no_conflict_to_resolve"):
        writes.keep_google_version(
            KeepGoogleVersionInput(
                command_id=str(uuid4()),
                calendar_block_id=block.id,
                expected_block_revision=after.revision,
            )
        )


def test_apply_ion_changes_rebases_onto_fresh_etag_never_reusing_the_stale_one(
    tmp_path,
):
    engine, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block, title="Renamed while offline")
    conflicted = _exhaust_to_conflict(writes, intent)
    assert conflicted.state == "conflict"

    # A background sync confirms Google's current ETag before the human
    # resolves the conflict. Apply Ion Changes must rebase onto this fresh
    # value, never the conflicted intent's own stale expected_provider_etag,
    # and never `If-Match: *`.
    with engine.begin() as connection:
        connection.execute(
            update(google_event_links)
            .where(google_event_links.c.calendar_block_id == block.id)
            .values(provider_etag='"fresh-etag-after-sync"')
        )
    current = next(item for item in calendar.status().blocks if item.id == block.id)

    apply_command_id = str(uuid4())
    applied = writes.apply_ion_changes(
        ApplyIonChangesInput(
            command_id=apply_command_id,
            calendar_block_id=block.id,
            expected_block_revision=current.revision,
        )
    )
    assert applied.state == "ready"
    with engine.connect() as connection:
        stored = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.id == applied.id
            )
        ).one()
    assert stored.expected_provider_etag == '"fresh-etag-after-sync"'
    assert stored.expected_provider_etag != "*"
    assert stored.predecessor_intent_id == intent.id
    assert json.loads(stored.desired_values_json)["title"] == "Renamed while offline"

    # The original conflicted row is resolved, not left dangling forever.
    with engine.connect() as connection:
        original = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.id == intent.id
            )
        ).one()
    assert original.state == "cancelled"
    assert original.failure_reason == "conflict_resolved_apply_ion"

    # A duplicate Apply Ion Changes submission is idempotent.
    replay = writes.apply_ion_changes(
        ApplyIonChangesInput(
            command_id=apply_command_id,
            calendar_block_id=block.id,
            expected_block_revision=current.revision,
        )
    )
    assert replay.id == applied.id

    # The rebased write must actually reach Google and finish, not stall:
    # dispatcher selects it, the preflight accepts the fresh authority, the
    # provider confirms, the conflict clears, and the preserved Ion value is
    # what Google now holds.
    plans = writes.ready(ReadyWriteIntentsInput())
    assert [plan.id for plan in plans] == [applied.id]
    assert plans[0].expected_provider_etag == '"fresh-etag-after-sync"'

    attempting = writes.begin_attempt(
        applied.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    assert attempting.state == "attempting"

    completed = writes.reconcile_patch(
        applied.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=ProviderEventInput(
                provider_event_id="synthetic-provider-event",
                provider_etag='"confirmed-after-apply-ion"',
                title="Renamed while offline",
                start=ProviderDateTime(
                    date_time="2030-01-01T09:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
                end=ProviderDateTime(
                    date_time="2030-01-01T10:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
            ),
        ),
    )
    assert completed.state == "completed"

    settled = next(item for item in calendar.status().blocks if item.id == block.id)
    assert settled.provider_write_state == "synced"
    assert settled.provider_write_detail == "confirmed"
    assert settled.title == "Renamed while offline"
    assert settled.provider_write_capability.eligible is True
    assert settled.provider_write_failure_class is None


def _split_series(tmp_path, *, preset_rule="RRULE:FREQ=WEEKLY", overrides=None):
    values = {"recurrence": [preset_rule]}
    values.update(overrides or {})
    return _connected(tmp_path, event_overrides=values)


def _split_edit(writes, block, original, **overrides):
    values = {
        "recurrence_scope": "this_and_following",
        "occurrence_original_start": original,
        "recurrence_risk_confirmed": True,
        "title": "Renamed from here forward",
    }
    values.update(overrides)
    return _edit(writes, block, command_id=str(uuid4()), **values)


def test_this_and_following_splits_the_series_into_two_masters(tmp_path):
    """Google parity: the old master is trimmed to stop before the selected
    occurrence and a new recurring master begins at it -- not one exception per
    future occurrence."""
    engine, calendar, writes, master = _split_series(tmp_path)
    original = ProviderDateTime(
        date_time="2030-01-15T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    trim = _split_edit(writes, master, original)
    assert trim.operation == "patch"
    assert trim.recurrence_scope == "series"
    assert trim.state == "ready"

    with engine.connect() as connection:
        rows = connection.execute(
            select(calendar_provider_write_intents).order_by(
                calendar_provider_write_intents.c.created_at
            )
        ).all()
    assert len(rows) == 2, "a split is exactly two provider operations"
    trim_row = next(row for row in rows if row.id == trim.id)
    create_row = next(row for row in rows if row.id != trim.id)

    # Old master trim: bounded preset plus generated termination, conditional
    # on the confirmed non-wildcard ETag.
    assert json.loads(trim_row.desired_values_json)["recurrence"] == [
        "RRULE:FREQ=WEEKLY;UNTIL=20300115T165959Z"
    ]
    assert trim_row.expected_provider_etag == '"synthetic-etag"'
    assert trim_row.expected_provider_etag != "*"

    # New master: create, ordered strictly behind the trim.
    assert create_row.operation == "create"
    assert create_row.recurrence_scope == "series"
    assert create_row.state == "queued"
    assert create_row.predecessor_intent_id == trim_row.id
    assert create_row.calendar_block_id != master.id
    desired = json.loads(create_row.desired_values_json)
    assert desired["recurrence"] == ["RRULE:FREQ=WEEKLY"]
    assert desired["title"] == "Renamed from here forward"
    assert desired["start"]["date_time"] == "2030-01-15T09:00:00-08:00"
    # Deterministic identity, fixed before any dispatch.
    assert create_row.provider_event_id == deterministic_google_event_id(
        create_row.calendar_block_id
    )
    # No attendee/reminder/conferencing field can appear in a bounded body.
    for forbidden in ("attendees", "reminders", "conferenceData", "attachments"):
        assert forbidden not in create_row.desired_values_json


def test_split_create_stays_blocked_until_the_trim_is_provider_confirmed(tmp_path):
    engine, calendar, writes, master = _split_series(tmp_path)
    original = ProviderDateTime(
        date_time="2030-01-15T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    trim = _split_edit(writes, master, original)

    # Only the trim may dispatch while it is unresolved.
    assert [plan.id for plan in writes.ready(ReadyWriteIntentsInput())] == [trim.id]
    writes.begin_attempt(
        trim.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    assert writes.ready(ReadyWriteIntentsInput()) == []

    # A retryable failure must not release the new master either.
    writes.random_fraction = lambda: 0.5
    writes.record_result(
        trim.id,
        RecordProviderWriteResultInput(
            stage="patch",
            result_class="retryable_backend",
            safe_reason="provider_backend_unavailable",
        ),
    )
    with engine.connect() as connection:
        pending_create = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.operation == "create"
            )
        ).one()
    assert pending_create.state == "queued"

    # Ordering survives a restart: it is durable state, not in-memory.
    restarted = CalendarWriteService(engine)
    restarted.recover(RecoverWriteIntentsInput(now="2099-01-01T00:00:00Z"))
    assert [plan.id for plan in restarted.ready(ReadyWriteIntentsInput())] == [trim.id]

    restarted.begin_attempt(
        trim.id,
        BeginWriteAttemptInput(expected_state="ready", executor_provenance="recovery"),
    )
    trimmed_master = ProviderEventInput(
        provider_event_id="synthetic-provider-event",
        provider_etag='"master-trimmed"',
        title="Synthetic event title",
        status="confirmed",
        recurrence=["RRULE:FREQ=WEEKLY;UNTIL=20300115T165959Z"],
        start=ProviderDateTime(
            date_time="2030-01-01T09:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
        end=ProviderDateTime(
            date_time="2030-01-01T10:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
    )
    assert (
        restarted.reconcile_patch(
            trim.id,
            ReconcileProviderPatchInput(
                resolution_kind="patch_response", event=trimmed_master
            ),
        ).state
        == "completed"
    )
    # Only now may the new master be created.
    released = restarted.ready(ReadyWriteIntentsInput())
    assert [plan.id for plan in released] == [pending_create.id]
    assert released[0].state == "ready"


def test_split_create_is_retired_when_the_trim_is_abandoned(tmp_path):
    """A cancelled trim must never leave the new future series behind to be
    created against a series that was never trimmed."""
    engine, calendar, writes, master = _split_series(tmp_path)
    original = ProviderDateTime(
        date_time="2030-01-15T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    trim = _split_edit(writes, master, original)
    conflicted = _exhaust_to_conflict(writes, trim)
    assert conflicted.state == "conflict"
    current = next(item for item in calendar.status().blocks if item.id == master.id)
    writes.keep_google_version(
        KeepGoogleVersionInput(
            command_id=str(uuid4()),
            calendar_block_id=master.id,
            expected_block_revision=current.revision,
        )
    )
    with engine.connect() as connection:
        create_row = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.operation == "create"
            )
        ).one()
    assert create_row.state == "cancelled"
    assert create_row.failure_reason == "series_split_abandoned"
    assert writes.ready(ReadyWriteIntentsInput()) == []


def test_split_refuses_the_first_occurrence_and_custom_recurrence(tmp_path):
    """The first occurrence makes a split identical to All events, and a custom
    provider rule cannot be faithfully continued -- both are refused truthfully
    rather than approximated."""
    _, _, writes, master = _split_series(tmp_path)
    first = ProviderDateTime(
        date_time="2030-01-01T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    with pytest.raises(
        CalendarValidationError, match="recurrence_split_at_first_occurrence"
    ):
        _split_edit(writes, master, first)

    _, _, custom_writes, custom_master = _split_series(
        tmp_path, preset_rule="RRULE:FREQ=WEEKLY;BYDAY=TU,TH"
    )
    with pytest.raises(CalendarValidationError, match="recurrence_split_unsupported"):
        _split_edit(
            custom_writes,
            custom_master,
            ProviderDateTime(
                date_time="2030-01-15T09:00:00-08:00",
                timezone="America/Los_Angeles",
            ),
        )


def test_split_inherits_ion_metadata_without_provider_authority(tmp_path):
    engine, calendar, writes, master = _split_series(tmp_path)
    calendar.set_category(
        master.id,
        CalendarCategoryInput(
            category="academic", category_subtype="class_section", expected_revision=1
        ),
    )
    current = next(item for item in calendar.status().blocks if item.id == master.id)
    original = ProviderDateTime(
        date_time="2030-01-15T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    _split_edit(writes, current, original)

    blocks = calendar.status().blocks
    new_master = next(
        item
        for item in blocks
        if item.id != master.id and item.recurrence_kind == "master"
    )
    # Ion-owned organisational metadata follows the series across the split.
    assert new_master.category == "academic"
    assert new_master.category_subtype == "class_section"
    assert new_master.flexibility == current.flexibility
    # Provider authority does not.
    assert new_master.provider_event_id != master.provider_event_id
    assert new_master.provider_write_state == "pending"
    with engine.connect() as connection:
        link = connection.execute(
            select(google_event_links).where(
                google_event_links.c.calendar_block_id == new_master.id
            )
        ).one()
    assert link.provider_etag is None
    assert link.link_state == "pending_create"
    assert link.recurring_event_id is None


def test_split_delete_trims_only_and_creates_no_future_series(tmp_path):
    engine, calendar, writes, master = _split_series(tmp_path)
    original = ProviderDateTime(
        date_time="2030-01-15T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    trim = _delete(
        writes,
        master,
        command_id=str(uuid4()),
        recurrence_scope="this_and_following",
        occurrence_original_start=original,
        series_confirmed=True,
    )
    assert trim.operation == "patch"
    assert trim.recurrence_scope == "series"
    with engine.connect() as connection:
        rows = connection.execute(select(calendar_provider_write_intents)).all()
    # Exactly one bounded trim: no new master, and no per-occurrence deletes.
    assert len(rows) == 1
    assert rows[0].operation == "patch"
    assert json.loads(rows[0].desired_values_json)["recurrence"] == [
        "RRULE:FREQ=WEEKLY;UNTIL=20300115T165959Z"
    ]
    assert len(calendar.status().blocks) == 1


@pytest.mark.parametrize(
    ("preset_rule", "expected"),
    [
        ("RRULE:FREQ=DAILY", "RRULE:FREQ=DAILY;UNTIL=20300115T165959Z"),
        (
            "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR",
            "RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR;UNTIL=20300115T165959Z",
        ),
        ("RRULE:FREQ=MONTHLY", "RRULE:FREQ=MONTHLY;UNTIL=20300115T165959Z"),
        ("RRULE:FREQ=YEARLY", "RRULE:FREQ=YEARLY;UNTIL=20300115T165959Z"),
    ],
)
def test_split_terminates_every_supported_preset(tmp_path, preset_rule, expected):
    _, _, writes, master = _split_series(tmp_path, preset_rule=preset_rule)
    trim = _split_edit(
        writes,
        master,
        ProviderDateTime(
            date_time="2030-01-15T09:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
    )
    with writes.engine.connect() as connection:
        row = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.id == trim.id
            )
        ).one()
    assert json.loads(row.desired_values_json)["recurrence"] == [expected]


def test_all_day_split_terminates_on_the_previous_civil_date(tmp_path):
    """No midnight instant is fabricated for an all-day series."""
    _, calendar, writes, master = _connected(
        tmp_path,
        event_overrides={
            "recurrence": ["RRULE:FREQ=WEEKLY"],
            "start": ProviderDateTime(date="2030-01-07"),
            "end": ProviderDateTime(date="2030-01-08"),
        },
    )
    trim = _split_edit(
        writes,
        master,
        ProviderDateTime(date="2030-01-21"),
        title="All-day from here",
    )
    with writes.engine.connect() as connection:
        rows = connection.execute(select(calendar_provider_write_intents)).all()
    trim_row = next(row for row in rows if row.id == trim.id)
    create_row = next(row for row in rows if row.id != trim.id)
    assert json.loads(trim_row.desired_values_json)["recurrence"] == [
        "RRULE:FREQ=WEEKLY;UNTIL=20300120"
    ]
    desired = json.loads(create_row.desired_values_json)
    assert desired["start"] == {"date": "2030-01-21"}
    assert desired["end"] == {"date": "2030-01-22"}
    assert "date_time" not in create_row.desired_values_json


def _confirm_trim(writes, trim_id, *, provenance="direct_human"):
    writes.begin_attempt(
        trim_id,
        BeginWriteAttemptInput(expected_state="ready", executor_provenance=provenance),
    )
    return writes.reconcile_patch(
        trim_id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=ProviderEventInput(
                provider_event_id="synthetic-provider-event",
                provider_etag='"master-trimmed"',
                title="Synthetic event title",
                status="confirmed",
                recurrence=["RRULE:FREQ=WEEKLY;UNTIL=20300115T165959Z"],
                start=ProviderDateTime(
                    date_time="2030-01-01T09:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
                end=ProviderDateTime(
                    date_time="2030-01-01T10:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
            ),
        ),
    )


def test_split_survives_restart_between_confirmed_trim_and_new_master_create(tmp_path):
    """Partial completion C: Google already holds the shortened old series. The
    future series must remain durable, resume the *same* deterministic identity,
    and never be reported as fully synced."""
    engine, calendar, writes, master = _split_series(tmp_path)
    original = ProviderDateTime(
        date_time="2030-01-15T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    trim = _split_edit(writes, master, original)
    with engine.connect() as connection:
        create_before = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.operation == "create"
            )
        ).one()
    assert _confirm_trim(writes, trim.id).state == "completed"

    # Crash here: a fresh service must resume the identical create.
    restarted = CalendarWriteService(engine)
    restarted.recover(RecoverWriteIntentsInput())
    plans = restarted.ready(ReadyWriteIntentsInput())
    assert [plan.id for plan in plans] == [create_before.id]
    assert plans[0].provider_event_id == create_before.provider_event_id
    assert plans[0].expected_provider_etag is None

    # The split is truthfully incomplete: the future series is still pending.
    future = next(
        item
        for item in CalendarService(engine).status().blocks
        if item.id == create_before.calendar_block_id
    )
    assert future.provider_write_state == "pending"
    assert future.provider_write_detail in ("queued", "ready")


def test_split_create_ambiguity_reconciles_without_duplicating_the_future_series(
    tmp_path,
):
    """Partial completion E: an ambiguous insert is resolved by looking up the
    deterministic id, never by inserting a second future series."""
    engine, calendar, writes, master = _split_series(tmp_path)
    trim = _split_edit(
        writes,
        master,
        ProviderDateTime(
            date_time="2030-01-15T09:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
    )
    _confirm_trim(writes, trim.id)
    create = writes.ready(ReadyWriteIntentsInput())[0]
    writes.begin_attempt(
        create.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    writes.random_fraction = lambda: 0.5
    ambiguous = writes.record_result(
        create.id,
        RecordProviderWriteResultInput(
            stage="insert",
            result_class="duplicate_or_ambiguous_create",
            safe_reason="provider_duplicate_or_ambiguous",
        ),
    )
    assert ambiguous.state == "ambiguous"

    # The bounded lookup finds the already-created future master and completes
    # the same intent.
    writes.begin_attempt(
        create.id,
        BeginWriteAttemptInput(
            expected_state="ambiguous", executor_provenance="recovery"
        ),
    )
    completed = writes.reconcile_create(
        create.id,
        ReconcileProviderCreateInput(
            resolution_kind="identity_lookup",
            event=ProviderEventInput(
                provider_event_id=create.provider_event_id,
                provider_etag='"future-master"',
                title="Renamed from here forward",
                status="confirmed",
                recurrence=["RRULE:FREQ=WEEKLY"],
                start=ProviderDateTime(
                    date_time="2030-01-15T09:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
                end=ProviderDateTime(
                    date_time="2030-01-15T10:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
            ),
        ),
    )
    assert completed.state == "completed"

    blocks = CalendarService(engine).status().blocks
    masters = [item for item in blocks if item.recurrence_kind == "master"]
    # Exactly two recurring masters: the trimmed original and one future series.
    assert len(masters) == 2
    assert len({item.provider_event_id for item in masters}) == 2
    future = next(item for item in masters if item.id != master.id)
    assert future.provider_write_state == "synced"
    assert future.title == "Renamed from here forward"


def test_split_terminal_create_failure_preserves_the_future_series_intent(tmp_path):
    """Partial completion F: a terminally failed future create is never
    silently discarded, and the old series is never silently restored."""
    engine, calendar, writes, master = _split_series(tmp_path)
    trim = _split_edit(
        writes,
        master,
        ProviderDateTime(
            date_time="2030-01-15T09:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
    )
    _confirm_trim(writes, trim.id)
    create = writes.ready(ReadyWriteIntentsInput())[0]
    writes.begin_attempt(
        create.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    failed = writes.record_result(
        create.id,
        RecordProviderWriteResultInput(
            stage="insert",
            result_class="terminal_provider_rejection",
            safe_reason="provider_permission_rejected",
        ),
    )
    assert failed.state == "failed"

    blocks = CalendarService(engine).status().blocks
    future = next(item for item in blocks if item.id == create.calendar_block_id)
    # The user's future series survives locally and reports truthfully.
    assert future.title == "Renamed from here forward"
    assert future.provider_write_state == "failed"
    assert future.provider_write_failure_class == "terminal_provider_rejection"
    # The trimmed old master is untouched -- no automatic rollback.
    trimmed = next(item for item in blocks if item.id == master.id)
    assert trimmed.recurrence_rules == ["RRULE:FREQ=WEEKLY;UNTIL=20300115T165959Z"]
    # And an explicit human action can still retry it.
    with engine.connect() as connection:
        preserved = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.id == create.id
            )
        ).one()
    assert preserved.state == "failed"
    assert json.loads(preserved.desired_values_json)["title"] == (
        "Renamed from here forward"
    )


def test_split_trim_rebases_onto_a_moved_master_etag(tmp_path):
    """G: drift on the master before the trim confirms is absorbed, not
    escalated. The trim re-aims at the freshly confirmed ETag and proceeds --
    never against a stale one and never a wildcard -- and the deterministic
    future series stays chained behind it rather than restarting."""
    engine, calendar, writes, master = _split_series(tmp_path)
    trim = _split_edit(
        writes,
        master,
        ProviderDateTime(
            date_time="2030-01-15T09:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
    )
    with engine.begin() as connection:
        connection.execute(
            update(google_event_links)
            .where(google_event_links.c.calendar_block_id == master.id)
            .values(provider_etag='"moved-on"')
        )
    attempting = writes.begin_attempt(
        trim.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    assert attempting.state == "attempting"
    with engine.connect() as connection:
        rearmed = connection.execute(
            select(calendar_provider_write_intents.c.expected_provider_etag).where(
                calendar_provider_write_intents.c.id == trim.id
            )
        ).scalar_one()
    assert rearmed == '"moved-on"'
    # The future series is still held behind this same trim.
    with engine.connect() as connection:
        create_row = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.operation == "create"
            )
        ).one()
    assert create_row.state == "queued"
    assert create_row.predecessor_intent_id == trim.id


def test_apply_ion_rechains_a_split_future_master_onto_the_new_trim(tmp_path):
    engine, calendar, writes, master = _split_series(tmp_path)
    trim = _split_edit(
        writes,
        master,
        ProviderDateTime(
            date_time="2030-01-15T09:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
    )
    _exhaust_to_conflict(writes, trim)
    current = next(item for item in calendar.status().blocks if item.id == master.id)
    applied = writes.apply_ion_changes(
        ApplyIonChangesInput(
            command_id=str(uuid4()),
            calendar_block_id=master.id,
            expected_block_revision=current.revision,
        )
    )
    with engine.connect() as connection:
        create_row = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.operation == "create"
            )
        ).one()
    # The future series follows the re-authorized trim instead of being lost.
    assert create_row.state == "queued"
    assert create_row.predecessor_intent_id == applied.id
    assert writes.ready(ReadyWriteIntentsInput())[0].id == applied.id


def _occurrence_conflict(tmp_path):
    """Drive a recurring master to a real occurrence-scoped conflict.

    Ordinary ETag drift on the master is absorbed automatically, so a genuine
    conflict needs a genuine contradiction: here the provider event is no
    longer a recurring master at all, which no rebase can honestly repair. No
    exception row is ever materialized, because a conflicted write never
    reconciles."""
    engine, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    original = ProviderDateTime(
        date_time="2030-01-08T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    intent = _edit(
        writes,
        master,
        recurrence_scope="occurrence",
        occurrence_original_start=original,
        title="Occurrence revised while offline",
    )
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    # No longer a recurring master: the series this occurrence belonged to
    # does not exist in that form any more.
    unmergeable_master = _recurring_provider_event(
        etag='"drifted-master-etag"', recurrence=None
    )
    instance = _recurring_provider_event(
        provider_event_id="synthetic-instance",
        etag='"instance-etag"',
        recurring_event_id="synthetic-provider-event",
        original_start=original,
    )
    conflicted = writes.resolve_occurrence(
        intent.id,
        ResolveProviderOccurrenceInput(master=unmergeable_master, instance=instance),
    )
    assert conflicted.state == "conflict"
    assert conflicted.failure_reason == "recurrence_master_changed"
    return engine, calendar, writes, master, original, intent, instance


def test_master_row_conflict_from_an_unmaterialized_occurrence_is_resolvable(tmp_path):
    """Regression: a conflicted occurrence never materializes an exception
    row, so the conflict is displayed on the recurring master's own row. Every
    human resolution action must therefore be able to target it -- otherwise
    the row renders "needs review" forever while every action reports that
    there is no conflict to resolve."""
    _, calendar, writes, master, _original, intent, _instance = _occurrence_conflict(
        tmp_path
    )
    projected = next(item for item in calendar.status().blocks if item.id == master.id)
    assert projected.recurrence_kind == "master"
    assert projected.provider_write_state == "conflict"

    # The projection displays a conflict, so review/resolution must reach it.
    diff = writes.review_differences(master.id)
    assert diff.changed_fields == ["title"]
    assert diff.desired_title == "Occurrence revised while offline"

    kept = writes.keep_google_version(
        KeepGoogleVersionInput(
            command_id=str(uuid4()),
            calendar_block_id=master.id,
            expected_block_revision=projected.revision,
        )
    )
    assert kept.id == intent.id
    assert kept.state == "cancelled"

    resolved = next(item for item in calendar.status().blocks if item.id == master.id)
    assert resolved.provider_write_state == "synced"
    assert resolved.provider_write_capability.eligible is True

    # The truthful state must survive a restart: a resolved conflict must not
    # come back as a phantom "needs review" row from a fresh service.
    restarted = CalendarService(writes.engine)
    after_restart = next(
        item for item in restarted.status().blocks if item.id == master.id
    )
    assert after_restart.provider_write_state == "synced"
    assert after_restart.provider_write_detail == "confirmed"
    assert after_restart.provider_write_capability.eligible is True
    # And a second resolution attempt is now truthfully a no-op rather than a
    # dead end, because nothing unresolved remains.
    with pytest.raises(CalendarValidationError, match="no_conflict_to_resolve"):
        writes.keep_google_version(
            KeepGoogleVersionInput(
                command_id=str(uuid4()),
                calendar_block_id=master.id,
                expected_block_revision=after_restart.revision,
            )
        )


def test_apply_ion_changes_for_an_occurrence_dispatches_against_fresh_authority(
    tmp_path,
):
    """Regression: Apply my Ion changes on a conflicted occurrence must rebase
    the *embedded recurrence identity* onto the freshly confirmed master ETag,
    not just the row's expected_provider_etag. Copying the stale identity made
    the new intent fail `begin_attempt`'s preflight and immediately re-conflict,
    so the write never reached Google and the UI stayed in 'applying'."""
    engine, calendar, writes, master, original, _intent, instance = (
        _occurrence_conflict(tmp_path)
    )
    # A read sync confirms Google's current master ETag after the conflict.
    with engine.begin() as connection:
        connection.execute(
            update(google_event_links)
            .where(google_event_links.c.calendar_block_id == master.id)
            .values(provider_etag='"drifted-master-etag"')
        )
    current = next(item for item in calendar.status().blocks if item.id == master.id)

    applied = writes.apply_ion_changes(
        ApplyIonChangesInput(
            command_id=str(uuid4()),
            calendar_block_id=master.id,
            expected_block_revision=current.revision,
        )
    )
    assert applied.state == "ready"

    # The rebased intent must carry the fresh master authority in both places.
    with engine.connect() as connection:
        stored = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.id == applied.id
            )
        ).one()
    stored_base = ProviderWriteValues.model_validate_json(stored.base_values_json)
    assert stored.expected_provider_etag == '"drifted-master-etag"'
    assert stored_base.recurrence_identity.master_provider_etag == (
        '"drifted-master-etag"'
    )
    assert stored_base.recurrence_identity.original_start == original

    # It must actually be dispatchable, not silently stranded.
    plans = writes.ready(ReadyWriteIntentsInput())
    assert [plan.id for plan in plans] == [applied.id]

    # And it must survive the dispatch preflight instead of re-conflicting.
    attempting = writes.begin_attempt(
        applied.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    assert attempting.state == "attempting"

    current_master = _recurring_provider_event(
        etag='"drifted-master-etag"', recurrence=["RRULE:FREQ=WEEKLY"]
    )
    resolved = writes.resolve_occurrence(
        applied.id,
        ResolveProviderOccurrenceInput(master=current_master, instance=instance),
    )
    assert resolved.state == "attempting"

    completed = writes.reconcile_patch(
        applied.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=instance.model_copy(
                update={
                    "provider_etag": '"instance-etag-2"',
                    "title": "Occurrence revised while offline",
                }
            ),
        ),
    )
    assert completed.state == "completed"

    blocks = calendar.status().blocks
    exception = next(item for item in blocks if item.recurrence_kind == "exception")
    assert exception.title == "Occurrence revised while offline"
    assert exception.provider_write_state == "synced"
    master_row = next(item for item in blocks if item.id == master.id)
    assert master_row.provider_write_state == "synced"


def test_apply_ion_changes_refuses_to_resurrect_a_provider_deleted_event(tmp_path):
    engine, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block)
    conflicted = _exhaust_to_conflict(writes, intent)
    assert conflicted.state == "conflict"

    # Google confirms (via a concurrent read-sync) that the event no longer
    # exists before the human resolves the conflict.
    with engine.begin() as connection:
        connection.execute(
            update(calendar_blocks)
            .where(calendar_blocks.c.id == block.id)
            .values(status="cancelled", provider_deleted_at="2030-01-02T00:00:00Z")
        )
    current = next(item for item in calendar.status().blocks if item.id == block.id)

    with pytest.raises(CalendarValidationError, match="provider_deleted"):
        writes.apply_ion_changes(
            ApplyIonChangesInput(
                command_id=str(uuid4()),
                calendar_block_id=block.id,
                expected_block_revision=current.revision,
            )
        )
    # Keep Google Version remains available to accept the deletion.
    kept = writes.keep_google_version(
        KeepGoogleVersionInput(
            command_id=str(uuid4()),
            calendar_block_id=block.id,
            expected_block_revision=current.revision,
        )
    )
    assert kept.state == "cancelled"


def test_review_differences_returns_only_bounded_normalized_fields(tmp_path):
    _, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block, title="Renamed while offline")
    conflicted = _exhaust_to_conflict(writes, intent)
    assert conflicted.state == "conflict"

    diff = writes.review_differences(block.id)
    assert diff.changed_fields == ["title"]
    assert diff.confirmed_title == "Synthetic event title"
    assert diff.desired_title == "Renamed while offline"
    # Only the changed field is populated; temporal/recurrence/status stay
    # unset rather than fabricated, and no raw provider object/ETag/ID
    # appears anywhere in the bounded output.
    assert diff.confirmed_start is None and diff.desired_start is None
    assert diff.confirmed_recurrence is None and diff.desired_recurrence is None
    assert diff.confirmed_status is None and diff.desired_status is None
    dumped = diff.model_dump()
    assert "provider_event_id" not in dumped
    assert "expected_provider_etag" not in dumped
    assert not any("etag" in key for key in dumped)


def test_delete_412_and_ambiguity_etag_drift_preserve_conflict(tmp_path):
    _, _, writes, block = _connected(tmp_path)
    intent = _delete(writes, block)
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    conflict = writes.record_result(
        intent.id,
        RecordProviderWriteResultInput(
            stage="delete",
            result_class="stale_precondition",
            safe_reason="stale_precondition",
        ),
    )
    assert conflict.state == "conflict"

    _, _, writes2, block2 = _connected(tmp_path)
    intent2 = _delete(writes2, block2)
    writes2.begin_attempt(
        intent2.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    writes2.record_result(
        intent2.id,
        RecordProviderWriteResultInput(
            stage="delete",
            result_class="retryable_transport",
            safe_reason="transport_failure",
        ),
    )
    writes2.begin_attempt(
        intent2.id,
        BeginWriteAttemptInput(
            expected_state="ambiguous", executor_provenance="recovery"
        ),
    )
    drift = writes2.reconcile_delete(
        intent2.id,
        ReconcileProviderDeleteInput(
            resolution_kind="identity_lookup",
            event=ProviderEventInput(
                provider_event_id=block2.provider_event_id,
                provider_etag='"changed-etag"',
                title="Synthetic event title",
                start=ProviderDateTime(
                    date_time="2030-01-01T09:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
                end=ProviderDateTime(
                    date_time="2030-01-01T10:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
            ),
        ),
    )
    assert drift.state == "conflict"
    assert drift.failure_reason == "provider_target_changed"


def test_refresh_tombstone_completes_pending_delete_without_resurrection(tmp_path):
    _, calendar, writes, block = _connected(tmp_path)
    intent = _delete(writes, block)
    calendar_id = calendar.status().calendars[0].id
    generation = str(uuid4())
    calendar.begin_sync(
        calendar_id, SyncBeginInput(generation=generation, mode="incremental")
    )
    calendar.apply_sync_page(
        calendar_id,
        SyncPageInput(
            generation=generation,
            events=[
                ProviderEventInput(
                    provider_event_id=block.provider_event_id,
                    provider_etag='"synthetic-delete-etag"',
                    status="cancelled",
                )
            ],
        ),
    )
    with calendar.engine.connect() as connection:
        row = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.id == intent.id
            )
        ).one()
    assert row.state == "completed"
    assert calendar.status().blocks[0].status == "cancelled"


def test_deterministic_google_event_id_is_stable_160_bit_base32hex():
    block_id = "11111111-1111-4111-8111-111111111111"
    first = deterministic_google_event_id(block_id)
    assert first == deterministic_google_event_id(block_id)
    assert len(first) == 32
    assert re.fullmatch(r"[0-9a-v]{32}", first)
    assert first != deterministic_google_event_id(
        "22222222-2222-4222-8222-222222222222"
    )
    assert "11111111" not in first


def test_full_jitter_is_deterministic_bounded_and_has_no_rapid_floor():
    assert full_jitter_delay_seconds(1, 0) == 0
    assert full_jitter_delay_seconds(1, 0.999) == 29
    assert full_jitter_delay_seconds(5, 0.5) == 150
    with pytest.raises(CalendarValidationError):
        full_jitter_delay_seconds(6, 0.5)
    with pytest.raises(CalendarValidationError):
        full_jitter_delay_seconds(1, 1)


def test_local_first_create_is_atomic_idempotent_pending_and_content_safe(tmp_path):
    engine, calendar, writes, _ = _connected(tmp_path)
    command_id = str(uuid4())
    created = _create(writes, calendar, command_id=command_id)
    repeated = _create(writes, calendar, command_id=command_id)
    assert repeated.id == created.id
    assert created.state == "ready"
    status = calendar.status()
    pending = next(
        block for block in status.blocks if block.id == created.calendar_block_id
    )
    assert pending.provider_write_state == "pending"
    assert pending.provider_write_detail == "ready"
    assert pending.title == "Synthetic owner-created event"
    assert pending.start_at == "2030-01-02T09:00:00-08:00"
    assert pending.end_at == "2030-01-02T10:00:00-08:00"

    with engine.connect() as connection:
        link = connection.execute(
            select(google_event_links).where(
                google_event_links.c.calendar_block_id == pending.id
            )
        ).one()
        assert link.link_state == "pending_create"
        assert link.provider_event_id == deterministic_google_event_id(pending.id)
        assert link.provider_etag is None
        assert connection.execute(
            select(calendar_blocks.c.id).where(calendar_blocks.c.id == pending.id)
        ).all() == [(pending.id,)]
        compact = connection.execute(
            select(calendar_provider_write_audit).where(
                calendar_provider_write_audit.c.intent_id == created.id
            )
        ).all()
        canonical = connection.execute(
            select(audit_events).where(audit_events.c.command_id == command_id)
        ).all()
    assert [row.action for row in compact] == [
        "write_intent_queued",
        "write_intent_ready",
    ]
    assert [row.action for row in canonical] == ["create_requested"]
    audit_text = json.dumps(
        [row._asdict() for row in compact] + [row._asdict() for row in canonical]
    )
    assert "Synthetic owner-created event" not in audit_text

    restarted = CalendarWriteService(engine)
    plans = restarted.ready(ReadyWriteIntentsInput(now="2030-01-02T00:00:00Z"))
    assert [plan.id for plan in plans] == [created.id]
    assert plans[0].provider_event_id == link.provider_event_id


def test_all_day_and_dst_create_semantics_are_preserved(tmp_path):
    _, calendar, writes, _ = _connected(tmp_path)
    all_day = _create(
        writes,
        calendar,
        title="Synthetic all-day event",
        date="2030-02-14",
        all_day=True,
        start_time=None,
        end_time=None,
        timezone=None,
    )
    all_day_plan = next(
        item
        for item in writes.ready(ReadyWriteIntentsInput(now="2030-01-01T00:00:00Z"))
        if item.id == all_day.id
    )
    assert all_day_plan.desired_values.start == ProviderDateTime(date="2030-02-14")
    assert all_day_plan.desired_values.end == ProviderDateTime(date="2030-02-15")
    block = next(
        item
        for item in calendar.status().blocks
        if item.id == all_day.calendar_block_id
    )
    assert block.temporal_kind == "all_day"
    assert block.start_date == "2030-02-14"
    assert block.end_date == "2030-02-15"
    assert block.start_at is None

    with pytest.raises(CalendarValidationError, match="skipped DST"):
        _create(
            writes,
            calendar,
            date="2030-03-10",
            start_time="02:15",
            end_time="03:15",
        )
    with pytest.raises(CalendarValidationError, match="ambiguous"):
        _create(
            writes,
            calendar,
            date="2030-11-03",
            start_time="01:15",
            end_time="02:15",
        )


def test_duplicate_and_restart_ambiguity_reconcile_the_same_provider_identity(tmp_path):
    engine, calendar, writes, _ = _connected(tmp_path)
    created = _create(writes, calendar)
    attempting = writes.begin_attempt(
        created.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    assert attempting.attempt_count == 1
    ambiguous = writes.record_result(
        created.id,
        RecordProviderWriteResultInput(
            stage="insert",
            result_class="duplicate_or_ambiguous_create",
            safe_reason="duplicate_id",
        ),
    )
    assert ambiguous.state == "ambiguous"

    restarted = CalendarWriteService(engine)
    plans = restarted.ready(ReadyWriteIntentsInput(now="2030-01-02T00:00:00Z"))
    assert len(plans) == 1
    assert plans[0].state == "ambiguous"
    lookup = restarted.begin_attempt(
        created.id,
        BeginWriteAttemptInput(
            expected_state="ambiguous", executor_provenance="recovery"
        ),
    )
    assert lookup.attempt_count == 2
    completed = restarted.reconcile_create(
        created.id,
        ReconcileProviderCreateInput(
            resolution_kind="identity_lookup",
            event=ProviderEventInput(
                provider_event_id=plans[0].provider_event_id,
                ical_uid="synthetic-created@example.invalid",
                provider_etag='"synthetic-created-etag"',
                provider_updated_at="2030-01-02T17:00:00Z",
                title="Synthetic owner-created event",
                start=ProviderDateTime(
                    date_time="2030-01-02T09:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
                end=ProviderDateTime(
                    date_time="2030-01-02T10:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
            ),
        ),
    )
    assert completed.state == "completed"
    block = next(
        item
        for item in calendar.status().blocks
        if item.id == created.calendar_block_id
    )
    assert block.provider_write_state == "synced"
    assert block.provider_write_detail == "confirmed"
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(google_event_links.c.link_state).where(
                    google_event_links.c.calendar_block_id == block.id
                )
            ).scalar_one()
            == "confirmed"
        )
        assert connection.execute(
            select(calendar_blocks.c.id).where(calendar_blocks.c.id == block.id)
        ).all() == [(block.id,)]


def test_absent_ambiguous_create_retries_same_id_then_obeys_ceiling(tmp_path):
    _, calendar, writes, _ = _connected(tmp_path)
    writes.random_fraction = lambda: 0.5
    created = _create(writes, calendar)
    plan = writes.ready(ReadyWriteIntentsInput(now="2030-01-02T00:00:00Z"))[0]
    provider_id = plan.provider_event_id
    writes.begin_attempt(
        created.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    writes.record_result(
        created.id,
        RecordProviderWriteResultInput(
            stage="insert",
            result_class="retryable_transport",
            safe_reason="transport_ambiguous",
        ),
    )
    writes.begin_attempt(
        created.id,
        BeginWriteAttemptInput(
            expected_state="ambiguous", executor_provenance="recovery"
        ),
    )
    retry = writes.record_result(
        created.id,
        RecordProviderWriteResultInput(
            stage="identity_lookup",
            result_class="provider_not_found",
            safe_reason="confirmed_absent",
        ),
    )
    assert retry.state == "retry_wait"
    assert retry.next_attempt_at is not None
    writes.recover(RecoverWriteIntentsInput(now="2100-01-01T00:00:00Z"))
    retried_plan = writes.ready(ReadyWriteIntentsInput(now="2100-01-01T00:00:00Z"))[0]
    assert retried_plan.provider_event_id == provider_id


@pytest.mark.parametrize(
    ("mutation", "state", "reason"),
    [
        ("calendar_read_only", "failed", "access_role_read_only"),
        ("calendar_deleted", "failed", "calendar_deleted"),
        ("account_read_only", "failed", "account_read_only"),
        ("reauth", "reauth_required", "reauth_required"),
    ],
)
def test_dispatch_rechecks_destination_and_account_capability(
    tmp_path, mutation, state, reason
):
    engine, calendar, writes, _ = _connected(tmp_path)
    created = _create(writes, calendar)
    with engine.begin() as connection:
        if mutation == "calendar_read_only":
            connection.execute(update(google_calendars).values(access_role="reader"))
        elif mutation == "calendar_deleted":
            connection.execute(
                update(google_calendars).values(
                    provider_deleted=True, enabled_in_ion=False
                )
            )
        elif mutation == "account_read_only":
            connection.execute(
                update(google_accounts).values(calendar_write_scope_state="read_only")
            )
        else:
            connection.execute(
                update(google_accounts).values(
                    auth_state="reauth_required",
                    calendar_write_scope_state="reauth_required",
                )
            )
    blocked = writes.begin_attempt(
        created.id,
        BeginWriteAttemptInput(expected_state="ready", executor_provenance="recovery"),
    )
    assert blocked.state == state
    assert blocked.failure_reason == reason


def test_capability_is_backend_derived_and_existing_read_grants_stay_read_only(
    tmp_path,
):
    _, calendar, writes, block = _connected(tmp_path, write=False)
    account = calendar.status().accounts[0]
    assert account.calendar_write_scope_state == "read_only"
    assert block.provider_write_capability.reason == "account_read_only"
    foundation = writes.foundation()
    assert foundation.accounts[0].write_capable is False
    with pytest.raises(CalendarValidationError, match="account_read_only"):
        _queue(writes, block)


@pytest.mark.parametrize(
    ("event_overrides", "reason"),
    [
        ({"has_attendees": True}, "attendees_present"),
        ({"provider_locked": True}, "provider_locked"),
        ({"provider_event_type": "special"}, "special_event"),
    ],
)
def test_provider_event_capability_rejects_unsafe_event_classes(
    tmp_path, event_overrides, reason
):
    _, calendar, writes, block = _connected(tmp_path, event_overrides=event_overrides)
    projected = calendar.status().blocks[0]
    assert projected.provider_write_capability.eligible is False
    assert projected.provider_write_capability.reason == reason
    assert projected.provider_delete_capability.eligible is False
    assert projected.provider_delete_capability.reason == reason
    with pytest.raises(CalendarValidationError, match=reason):
        _edit(writes, block)
    with pytest.raises(CalendarValidationError, match=reason):
        _delete(writes, block)


def test_safe_recurring_master_exposes_scoped_write_capabilities(tmp_path):
    _, calendar, writes, block = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=DAILY"]}
    )
    projected = calendar.status().blocks[0]
    assert projected.recurrence_kind == "master"
    assert projected.recurrence_preset == "daily"
    assert projected.provider_write_capability.eligible is True
    assert projected.provider_delete_capability.eligible is True
    assert writes.foundation().blocks[0].eligible is True
    with pytest.raises(CalendarValidationError, match="single scope"):
        _edit(writes, block)
    assert (
        _edit(writes, block, recurrence_scope="series", title="Series title").state
        == "ready"
    )


def _recurring_provider_event(
    *,
    provider_event_id="synthetic-provider-event",
    etag='"synthetic-etag"',
    title="Synthetic event title",
    recurrence=None,
    recurring_event_id=None,
    original_start=None,
    status="confirmed",
):
    return ProviderEventInput(
        provider_event_id=provider_event_id,
        provider_etag=etag,
        title=title,
        status=status,
        start=(
            None
            if status == "cancelled"
            else ProviderDateTime(
                date_time="2030-01-08T09:00:00-08:00",
                timezone="America/Los_Angeles",
            )
        ),
        end=(
            None
            if status == "cancelled"
            else ProviderDateTime(
                date_time="2030-01-08T10:00:00-08:00",
                timezone="America/Los_Angeles",
            )
        ),
        recurrence=recurrence or [],
        recurring_event_id=recurring_event_id,
        original_start=original_start,
    )


def test_occurrence_resolution_uses_master_plus_original_start_and_preserves_exception(
    tmp_path,
):
    _, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    original = ProviderDateTime(
        date_time="2030-01-08T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    intent = _edit(
        writes,
        master,
        recurrence_scope="occurrence",
        occurrence_original_start=original,
        title="One revised occurrence",
    )
    projected = calendar.status().blocks[0]
    assert projected.title == "Synthetic event title"
    assert projected.provider_write_recurrence_scope == "occurrence"
    assert projected.provider_write_original_start == original

    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    master_event = _recurring_provider_event(recurrence=["RRULE:FREQ=WEEKLY"])
    instance = _recurring_provider_event(
        provider_event_id="synthetic-instance",
        etag='"instance-etag"',
        title="Synthetic event title",
        recurring_event_id="synthetic-provider-event",
        original_start=original,
    )
    resolved = writes.resolve_occurrence(
        intent.id,
        ResolveProviderOccurrenceInput(master=master_event, instance=instance),
    )
    assert resolved.provider_event_id == "synthetic-instance"
    assert resolved.expected_provider_etag == '"instance-etag"'

    confirmed = instance.model_copy(
        update={"provider_etag": '"instance-etag-2"', "title": "One revised occurrence"}
    )
    assert (
        writes.reconcile_patch(
            intent.id,
            ReconcileProviderPatchInput(
                resolution_kind="patch_response", event=confirmed
            ),
        ).state
        == "completed"
    )
    blocks = calendar.status().blocks
    assert len(blocks) == 2
    persisted_master = next(
        block for block in blocks if block.recurrence_kind == "master"
    )
    exception = next(block for block in blocks if block.recurrence_kind == "exception")
    assert persisted_master.title == "Synthetic event title"
    assert exception.title == "One revised occurrence"
    assert exception.provider_event_id == "synthetic-instance"
    exception_id = exception.id

    second = _edit(
        writes,
        exception,
        recurrence_scope="occurrence",
        occurrence_original_start=original,
        title="Same exception, revised again",
    )
    writes.begin_attempt(
        second.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    current_instance = confirmed.model_copy(
        update={"provider_etag": '"instance-etag-2"'}
    )
    writes.resolve_occurrence(
        second.id,
        ResolveProviderOccurrenceInput(master=master_event, instance=current_instance),
    )
    writes.reconcile_patch(
        second.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=current_instance.model_copy(
                update={
                    "provider_etag": '"instance-etag-3"',
                    "title": "Same exception, revised again",
                }
            ),
        ),
    )
    blocks = calendar.status().blocks
    exceptions = [block for block in blocks if block.recurrence_kind == "exception"]
    assert len(exceptions) == 1
    assert exceptions[0].id == exception_id


def test_completed_occurrence_write_clears_projection_and_next_stays_editable(
    tmp_path,
):
    _, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    first_original = ProviderDateTime(
        date_time="2030-01-08T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    first_intent = _edit(
        writes,
        master,
        recurrence_scope="occurrence",
        occurrence_original_start=first_original,
        title="First occurrence revised",
    )
    mid_flight = calendar.status().blocks[0]
    assert mid_flight.provider_write_recurrence_scope == "occurrence"

    writes.begin_attempt(
        first_intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    master_event = _recurring_provider_event(recurrence=["RRULE:FREQ=WEEKLY"])
    instance = _recurring_provider_event(
        provider_event_id="synthetic-instance",
        etag='"instance-etag"',
        recurring_event_id="synthetic-provider-event",
        original_start=first_original,
    )
    writes.resolve_occurrence(
        first_intent.id,
        ResolveProviderOccurrenceInput(master=master_event, instance=instance),
    )
    confirmed = instance.model_copy(
        update={
            "provider_etag": '"instance-etag-2"',
            "title": "First occurrence revised",
        }
    )
    completed = writes.reconcile_patch(
        first_intent.id,
        ReconcileProviderPatchInput(resolution_kind="patch_response", event=confirmed),
    )
    assert completed.state == "completed"

    after = next(block for block in calendar.status().blocks if block.id == master.id)
    assert after.provider_write_recurrence_scope is None
    assert after.provider_write_operation is None
    assert after.provider_write_original_start is None
    assert after.provider_write_capability.eligible is True

    second_original = ProviderDateTime(
        date_time="2030-01-15T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    second_intent = _edit(
        writes,
        after,
        command_id=str(uuid4()),
        recurrence_scope="occurrence",
        occurrence_original_start=second_original,
        title="Second occurrence revised",
    )
    assert second_intent.state == "ready"


def test_edit_write_intent_is_idempotent_for_duplicate_command_id(tmp_path):
    _, calendar, writes, block = _connected(tmp_path)
    command_id = str(uuid4())
    first = _edit(writes, block, command_id=command_id)
    second = _edit(writes, block, command_id=command_id)
    assert second.id == first.id
    status = calendar.status().blocks[0]
    assert status.provider_write_state == "pending"
    with writes.engine.connect() as connection:
        rows = connection.execute(
            select(calendar_provider_write_intents.c.id).where(
                calendar_provider_write_intents.c.command_id == command_id
            )
        ).all()
    assert len(rows) == 1


def test_occurrence_time_move_enters_dispatch_with_preserved_duration(tmp_path):
    engine, _, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    original = ProviderDateTime(
        date_time="2030-01-08T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    intent = _edit(
        writes,
        master,
        edit_kind="move",
        recurrence_scope="occurrence",
        occurrence_original_start=original,
        title=None,
        start_date="2030-01-09",
        start_time="13:15",
        timezone="America/Los_Angeles",
    )
    plan = writes.ready(ReadyWriteIntentsInput())[0]
    assert plan.id == intent.id
    assert plan.desired_values.start.date_time == "2030-01-09T13:15:00-08:00"
    assert plan.desired_values.end.date_time == "2030-01-09T14:15:00-08:00"

    attempting = writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    assert attempting.state == "attempting"
    assert attempting.attempt_count == 1
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(calendar_provider_write_audit.c.action)
                .where(calendar_provider_write_audit.c.intent_id == intent.id)
                .order_by(calendar_provider_write_audit.c.occurred_at)
            )
            .scalars()
            .all()[-1]
            == "write_attempt_started"
        )


def test_master_nonterminal_write_serializes_explicit_occurrence_siblings(tmp_path):
    _, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    master_event = _recurring_provider_event(recurrence=["RRULE:FREQ=WEEKLY"])

    def confirm_exception(original: ProviderDateTime, provider_id: str, title: str):
        intent = _edit(
            writes,
            master,
            recurrence_scope="occurrence",
            occurrence_original_start=original,
            title=title,
        )
        writes.begin_attempt(
            intent.id,
            BeginWriteAttemptInput(
                expected_state="ready", executor_provenance="direct_human"
            ),
        )
        instance = _recurring_provider_event(
            provider_event_id=provider_id,
            etag=f'"{provider_id}-etag"',
            recurring_event_id="synthetic-provider-event",
            original_start=original,
        )
        writes.resolve_occurrence(
            intent.id,
            ResolveProviderOccurrenceInput(master=master_event, instance=instance),
        )
        writes.reconcile_patch(
            intent.id,
            ReconcileProviderPatchInput(
                resolution_kind="patch_response",
                event=instance.model_copy(
                    update={
                        "provider_etag": f'"{provider_id}-etag-2"',
                        "title": title,
                    }
                ),
            ),
        )

    first_original = ProviderDateTime(
        date_time="2030-01-08T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    second_original = ProviderDateTime(
        date_time="2030-01-15T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    confirm_exception(first_original, "synthetic-instance-one", "First exception")
    confirm_exception(second_original, "synthetic-instance-two", "Second exception")

    exceptions = [
        item for item in calendar.status().blocks if item.recurrence_kind == "exception"
    ]
    first = next(item for item in exceptions if item.title == "First exception")
    pending = _edit(
        writes,
        first,
        edit_kind="move",
        recurrence_scope="occurrence",
        occurrence_original_start=first_original,
        title=None,
        start_date="2030-01-09",
        start_time="13:15",
        timezone="America/Los_Angeles",
    )
    assert pending.state == "ready"
    ready = writes.ready(ReadyWriteIntentsInput())[0]
    assert ready.id == pending.id
    assert ready.desired_values.start.date_time == "2030-01-09T13:15:00-08:00"
    assert ready.desired_values.end.date_time == "2030-01-09T14:15:00-08:00"

    projected = calendar.status().blocks
    targeted = next(item for item in projected if item.id == first.id)
    sibling = next(
        item
        for item in projected
        if item.recurrence_kind == "exception" and item.id != first.id
    )
    assert targeted.provider_write_state == "pending"
    assert targeted.provider_write_overlay.start == ready.desired_values.start
    assert targeted.provider_write_overlay.end == ready.desired_values.end
    assert sibling.provider_write_state == "synced"
    # Provider dispatch serializes; the owner does not. A sibling occurrence
    # stays directly editable while another occurrence's write is unsettled.
    assert sibling.provider_write_capability.reason == "eligible"
    assert sibling.provider_write_capability.eligible is True
    assert sibling.provider_write_overlay is None
    assert sibling.provider_write_operation is None
    foundation = {item.calendar_block_id: item for item in writes.foundation().blocks}
    assert foundation[first.id].reason == "write_pending"
    assert foundation[sibling.id].reason == "write_pending"

    attempting = writes.begin_attempt(
        pending.id,
        BeginWriteAttemptInput(expected_state="ready", executor_provenance="recovery"),
    )
    assert attempting.state == "attempting"
    current_instance = _recurring_provider_event(
        provider_event_id="synthetic-instance-one",
        etag='"synthetic-instance-one-etag-2"',
        title="First exception",
        recurring_event_id="synthetic-provider-event",
        original_start=first_original,
    )
    writes.resolve_occurrence(
        pending.id,
        ResolveProviderOccurrenceInput(master=master_event, instance=current_instance),
    )
    completed = writes.reconcile_patch(
        pending.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=current_instance.model_copy(
                update={
                    "provider_etag": '"synthetic-instance-one-etag-3"',
                    "start": ready.desired_values.start,
                    "end": ready.desired_values.end,
                }
            ),
        ),
    )
    assert completed.state == "completed"

    refreshed = calendar.status().blocks
    reconciled_target = next(item for item in refreshed if item.id == first.id)
    released_sibling = next(
        item
        for item in refreshed
        if item.recurrence_kind == "exception" and item.id != first.id
    )
    assert reconciled_target.provider_write_state == "synced"
    assert reconciled_target.provider_write_detail == "confirmed"
    assert reconciled_target.provider_write_overlay is None
    assert released_sibling.provider_write_capability.eligible is True
    released_foundation = {
        item.calendar_block_id: item for item in writes.foundation().blocks
    }
    assert released_foundation[first.id].eligible is True
    assert released_foundation[sibling.id].eligible is True


def test_occurrence_conflict_preserves_intent_and_releases_unrelated_sibling(
    tmp_path,
):
    _, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    first_original = ProviderDateTime(
        date_time="2030-01-08T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    second_original = ProviderDateTime(
        date_time="2030-01-15T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    first_intent = _edit(
        writes,
        master,
        recurrence_scope="occurrence",
        occurrence_original_start=first_original,
        title="First occurrence revised",
    )
    writes.begin_attempt(
        first_intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )

    mid_flight = next(
        block for block in calendar.status().blocks if block.id == master.id
    )
    assert mid_flight.provider_write_recurrence_scope == "occurrence"
    assert mid_flight.provider_write_capability.eligible is True

    # Provider drift: Google's master no longer matches the etag Ion recorded
    # when the occurrence write was queued, and the series no longer exists in
    # that form, so resolution must conflict rather than patch a stale target.
    unmergeable_master = _recurring_provider_event(
        etag='"drifted-master-etag"', recurrence=None
    )
    instance = _recurring_provider_event(
        provider_event_id="synthetic-instance",
        etag='"instance-etag"',
        recurring_event_id="synthetic-provider-event",
        original_start=first_original,
    )
    conflicted = writes.resolve_occurrence(
        first_intent.id,
        ResolveProviderOccurrenceInput(master=unmergeable_master, instance=instance),
    )
    assert conflicted.state == "conflict"
    assert conflicted.failure_reason == "recurrence_master_changed"

    with_conflict = next(
        block for block in calendar.status().blocks if block.id == master.id
    )
    # Occurrence A's identity stays visible so the renderer can still single
    # it out, and its own row would show the true conflict state.
    assert with_conflict.provider_write_recurrence_scope == "occurrence"
    assert with_conflict.provider_write_original_start == first_original
    assert with_conflict.provider_write_operation == "patch"

    with writes.engine.connect() as connection:
        stored = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.id == first_intent.id
            )
        ).one()
    assert stored.state == "conflict"
    assert json.loads(stored.desired_values_json)["title"] == "First occurrence revised"

    # An unrelated, untouched occurrence of the same master must now be
    # editable against current confirmed provider state -- not blocked by
    # A's unresolved conflict, and not somehow mutating A.
    second_intent = _edit(
        writes,
        with_conflict,
        command_id=str(uuid4()),
        recurrence_scope="occurrence",
        occurrence_original_start=second_original,
        title="Second occurrence revised",
    )
    assert second_intent.state == "ready"
    with writes.engine.connect() as connection:
        second_stored = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.id == second_intent.id
            )
        ).one()
    second_base = json.loads(second_stored.base_values_json)
    assert (
        second_base["recurrence_identity"]["original_start"]["date_time"]
        == second_original.date_time
    )
    assert json.loads(second_stored.desired_values_json)["title"] == (
        "Second occurrence revised"
    )
    # A's own stale intent is untouched by B's new write.
    with writes.engine.connect() as connection:
        still_conflicted = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.id == first_intent.id
            )
        ).one()
    assert still_conflicted.state == "conflict"

    # While B's own write is genuinely in flight, a third occurrence write is
    # still *accepted* -- provider dispatch serializes, the owner does not.
    writes.begin_attempt(
        second_intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    third_original = ProviderDateTime(
        date_time="2030-01-22T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    third_intent = _edit(
        writes,
        with_conflict,
        command_id=str(uuid4()),
        recurrence_scope="occurrence",
        occurrence_original_start=third_original,
        title="Third occurrence revised",
    )
    assert third_intent.state == "queued", (
        "it waits behind the in-flight write rather than dispatching in parallel"
    )
    assert writes.ready(ReadyWriteIntentsInput()) == [], (
        "nothing new may be dispatched while B is attempting"
    )

    # The owner acting again on A's own occurrence is likewise accepted, not
    # refused: acting again is their answer to the earlier outcome.
    retried = _edit(
        writes,
        with_conflict,
        command_id=str(uuid4()),
        recurrence_scope="occurrence",
        occurrence_original_start=first_original,
        title="Retried first occurrence",
    )
    assert retried.state == "queued"


def test_materialized_occurrence_conflict_releases_unrelated_materialized_sibling(
    tmp_path,
):
    """Two occurrences of the same recurring master are each independently
    materialized as their own `exception` CalendarBlock row. A conflict on
    one materialized occurrence must not permanently lock the other,
    already-materialized sibling out of editing (the read-projection
    equivalent of `_predecessor_blocks_new_write`'s write-path release)."""
    _, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    first_original = ProviderDateTime(
        date_time="2030-01-08T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    second_original = ProviderDateTime(
        date_time="2030-01-15T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    master_event = _recurring_provider_event(recurrence=["RRULE:FREQ=WEEKLY"])

    def _materialize(block, original, *, provider_event_id, title):
        intent = _edit(
            writes,
            block,
            command_id=str(uuid4()),
            recurrence_scope="occurrence",
            occurrence_original_start=original,
            title=title,
        )
        writes.begin_attempt(
            intent.id,
            BeginWriteAttemptInput(
                expected_state="ready", executor_provenance="direct_human"
            ),
        )
        instance = _recurring_provider_event(
            provider_event_id=provider_event_id,
            etag=f'"{provider_event_id}-etag"',
            recurring_event_id="synthetic-provider-event",
            original_start=original,
        )
        writes.resolve_occurrence(
            intent.id,
            ResolveProviderOccurrenceInput(master=master_event, instance=instance),
        )
        writes.reconcile_patch(
            intent.id,
            ReconcileProviderPatchInput(
                resolution_kind="patch_response",
                event=instance.model_copy(
                    update={
                        "provider_etag": f'"{provider_event_id}-etag-2"',
                        "title": title,
                    }
                ),
            ),
        )
        return instance

    # Materialize occurrence A as its own exception row.
    first_instance = _materialize(
        master,
        first_original,
        provider_event_id="synthetic-instance-a",
        title="First occurrence revised",
    )
    after_first = next(
        block for block in calendar.status().blocks if block.id == master.id
    )
    # Materialize occurrence B as a separate exception row.
    _materialize(
        after_first,
        second_original,
        provider_event_id="synthetic-instance-b",
        title="Second occurrence revised",
    )

    blocks = calendar.status().blocks
    exception_a = next(
        block
        for block in blocks
        if block.recurrence_kind == "exception"
        and block.title == "First occurrence revised"
    )
    exception_b = next(
        block
        for block in blocks
        if block.recurrence_kind == "exception"
        and block.title == "Second occurrence revised"
    )
    assert exception_a.provider_write_capability.eligible is True
    assert exception_b.provider_write_capability.eligible is True

    # Edit A again and force a conflict through provider master drift.
    third_intent = _edit(
        writes,
        exception_a,
        command_id=str(uuid4()),
        recurrence_scope="occurrence",
        occurrence_original_start=first_original,
        title="First occurrence revised again",
    )
    writes.begin_attempt(
        third_intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    unmergeable_master = _recurring_provider_event(
        etag='"drifted-master-etag"', recurrence=None
    )
    conflicted = writes.resolve_occurrence(
        third_intent.id,
        ResolveProviderOccurrenceInput(
            master=unmergeable_master,
            instance=first_instance.model_copy(
                update={"provider_etag": '"synthetic-instance-a-etag-2"'}
            ),
        ),
    )
    assert conflicted.state == "conflict"

    after_conflict = calendar.status().blocks
    still_exception_a = next(
        block for block in after_conflict if block.id == exception_a.id
    )
    still_exception_b = next(
        block for block in after_conflict if block.id == exception_b.id
    )
    # A's own materialized row truthfully shows the conflict...
    assert still_exception_a.provider_write_state == "conflict"
    assert still_exception_a.provider_write_capability.eligible is True
    # ...but B, a separate already-materialized occurrence, must not be
    # permanently locked out merely because A is unresolved.
    assert still_exception_b.provider_write_state == "synced"
    assert still_exception_b.provider_write_capability.eligible is True

    # B genuinely accepts a new write -- it is not just displayed as
    # eligible but actually writable.
    fourth_intent = _edit(
        writes,
        still_exception_b,
        command_id=str(uuid4()),
        recurrence_scope="occurrence",
        occurrence_original_start=second_original,
        title="Second occurrence revised again",
    )
    assert fourth_intent.state == "ready"


def test_preexisting_same_master_occurrence_writes_dispatch_serially(tmp_path):
    engine, _, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    original = ProviderDateTime(
        date_time="2030-01-08T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    first = _edit(
        writes,
        master,
        recurrence_scope="occurrence",
        occurrence_original_start=original,
        title="First serialized change",
    )
    second_id = str(uuid4())
    with engine.begin() as connection:
        first_row = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.id == first.id
            )
        ).one()
        second_values = dict(first_row._mapping)
        second_values.update(
            id=second_id,
            command_id=str(uuid4()),
            sequence=first_row.sequence + 1,
            predecessor_intent_id=None,
            created_at="2099-01-01T00:00:00Z",
            updated_at="2099-01-01T00:00:00Z",
        )
        connection.execute(
            insert(calendar_provider_write_intents).values(**second_values)
        )

    initially_ready = writes.ready(ReadyWriteIntentsInput())
    assert [plan.id for plan in initially_ready] == [first.id]
    writes.begin_attempt(
        first.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    master_event = _recurring_provider_event(recurrence=["RRULE:FREQ=WEEKLY"])
    instance = _recurring_provider_event(
        provider_event_id="synthetic-instance-one",
        etag='"synthetic-instance-one-etag"',
        recurring_event_id="synthetic-provider-event",
        original_start=original,
    )
    writes.resolve_occurrence(
        first.id,
        ResolveProviderOccurrenceInput(master=master_event, instance=instance),
    )
    writes.reconcile_patch(
        first.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=instance.model_copy(
                update={
                    "provider_etag": '"synthetic-instance-one-etag-2"',
                    "title": "First serialized change",
                }
            ),
        ),
    )

    next_ready = writes.ready(ReadyWriteIntentsInput())
    assert [plan.id for plan in next_ready] == [second_id]
    second_attempt = writes.begin_attempt(
        second_id,
        BeginWriteAttemptInput(expected_state="ready", executor_provenance="recovery"),
    )
    assert second_attempt.state == "attempting"
    assert second_attempt.attempt_count == 1


def test_recurrence_scope_confirmation_and_target_isolation(tmp_path):
    _, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=DAILY"]}
    )
    # A series-wide edit preserves every occurrence and stays reversible, so it
    # needs no risk acknowledgement to be accepted.
    series_edit = _edit(
        writes,
        master,
        recurrence_scope="series",
        title=None,
        recurrence="weekly",
        recurrence_risk_confirmed=False,
    )
    plan = writes.ready(ReadyWriteIntentsInput())[0]
    assert series_edit.recurrence_scope == "series"
    assert plan.provider_event_id == "synthetic-provider-event"
    assert plan.changed_fields == ["recurrence"]
    assert plan.desired_values.recurrence == ["RRULE:FREQ=WEEKLY"]

    writes.begin_attempt(
        series_edit.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    writes.reconcile_patch(
        series_edit.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=_recurring_provider_event(
                etag='"series-etag-2"', recurrence=["RRULE:FREQ=WEEKLY"]
            ),
        ),
    )
    latest_master = next(
        block for block in calendar.status().blocks if block.recurrence_kind == "master"
    )
    series_delete = _delete(
        writes,
        latest_master,
        recurrence_scope="series",
        series_confirmed=True,
    )
    assert series_delete.operation == "delete_series"
    assert writes.ready(ReadyWriteIntentsInput())[0].provider_event_id == (
        "synthetic-provider-event"
    )


def test_occurrence_master_etag_drift_rebases_instead_of_conflicting(tmp_path):
    _, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=MONTHLY"]}
    )
    original = ProviderDateTime(
        date_time="2030-02-01T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    intent = _delete(
        writes,
        master,
        recurrence_scope="occurrence",
        occurrence_original_start=original,
    )
    assert intent.operation == "cancel_occurrence"
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    drifted_master = _recurring_provider_event(
        etag='"changed-master-etag"', recurrence=["RRULE:FREQ=MONTHLY"]
    )
    instance = _recurring_provider_event(
        provider_event_id="synthetic-instance",
        etag='"instance-etag"',
        recurring_event_id="synthetic-provider-event",
        original_start=original,
    )
    resolved = writes.resolve_occurrence(
        intent.id,
        ResolveProviderOccurrenceInput(master=drifted_master, instance=instance),
    )
    # The master moved, but it is still the same recurring master and still
    # writable, and this master was just fetched from the provider -- so its
    # ETag is adopted and the occurrence write proceeds.
    assert resolved.state == "attempting"
    assert resolved.expected_provider_etag == '"instance-etag"'
    assert (
        resolved.base_values.recurrence_identity.master_provider_etag
        == '"changed-master-etag"'
    )
    projected = next(item for item in calendar.status().blocks if item.id == master.id)
    assert projected.provider_write_state == "pending"


def test_invalid_occurrence_resolution_is_a_truthful_conflict(tmp_path):
    _, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    original = ProviderDateTime(
        date_time="2030-01-08T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    intent = _edit(
        writes,
        master,
        edit_kind="move",
        recurrence_scope="occurrence",
        occurrence_original_start=original,
        title=None,
        start_date="2030-01-08",
        start_time="13:15",
        timezone="America/Los_Angeles",
    )
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    conflict = writes.record_result(
        intent.id,
        RecordProviderWriteResultInput(
            stage="instance_resolution",
            result_class="invalid_target",
            safe_reason="occurrence_resolution_rejected",
        ),
    )
    assert conflict.state == "conflict"
    assert conflict.failure_class == "stale_precondition"
    assert conflict.failure_reason == "occurrence_resolution_rejected"
    projected = next(item for item in calendar.status().blocks if item.id == master.id)
    assert projected.provider_write_state == "conflict"


def test_recovery_rearms_a_failed_occurrence_after_master_etag_drift(
    tmp_path,
):
    engine, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    original = ProviderDateTime(
        date_time="2030-01-08T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    intent = _edit(
        writes,
        master,
        edit_kind="resize",
        recurrence_scope="occurrence",
        occurrence_original_start=original,
        title=None,
        end_date="2030-01-08",
        end_time="10:30",
        timezone="America/Los_Angeles",
    )
    attempting = writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    failed = _transition(writes, attempting, "failed", result="invalid_target")
    with engine.begin() as connection:
        connection.execute(
            update(calendar_provider_write_intents)
            .where(calendar_provider_write_intents.c.id == failed.id)
            .values(failure_reason="provider_rejected_target")
        )

    calendar_id = calendar.status().calendars[0].id
    generation = str(uuid4())
    calendar.begin_sync(
        calendar_id, SyncBeginInput(generation=generation, mode="incremental")
    )
    calendar.apply_sync_page(
        calendar_id,
        SyncPageInput(
            generation=generation,
            events=[
                ProviderEventInput(
                    provider_event_id="synthetic-provider-event",
                    provider_etag='"synthetic-etag-v2"',
                    title="Synthetic event title",
                    start=ProviderDateTime(
                        date_time="2030-01-01T09:00:00-08:00",
                        timezone="America/Los_Angeles",
                    ),
                    end=ProviderDateTime(
                        date_time="2030-01-01T10:00:00-08:00",
                        timezone="America/Los_Angeles",
                    ),
                    recurrence=["RRULE:FREQ=WEEKLY"],
                )
            ],
        ),
    )
    assert (
        next(
            item for item in calendar.status().blocks if item.id == master.id
        ).provider_write_state
        == "failed"
    )

    recovered = writes.recover(RecoverWriteIntentsInput())
    assert recovered.failed_occurrence_to_conflict == 1
    stored = next(item for item in writes.foundation().pending if item.id == intent.id)
    # The rejection described a target that has since moved, so the owner's
    # intent is re-armed against the confirmed master and retried. Recovery
    # never manufactures a review task out of ordinary drift.
    assert stored.state == "ready"
    assert stored.failure_class is None
    plan = writes.ready(ReadyWriteIntentsInput())[0]
    assert plan.id == intent.id
    assert (
        plan.base_values.recurrence_identity.master_provider_etag
        == '"synthetic-etag-v2"'
    )
    with engine.connect() as connection:
        actions = (
            connection.execute(
                select(calendar_provider_write_audit.c.action).where(
                    calendar_provider_write_audit.c.intent_id == intent.id
                )
            )
            .scalars()
            .all()
        )
    assert "write_intent_ready" in actions
    # The owner sees a change still on its way, not a decision to make.
    assert (
        next(
            item for item in calendar.status().blocks if item.id == master.id
        ).provider_write_state
        == "pending"
    )


def test_ambiguous_occurrence_cancel_retries_when_exact_instance_is_unchanged(
    tmp_path,
):
    _, _, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    original = ProviderDateTime(
        date_time="2030-01-08T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    intent = _delete(
        writes,
        master,
        recurrence_scope="occurrence",
        occurrence_original_start=original,
    )
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    master_event = _recurring_provider_event(recurrence=["RRULE:FREQ=WEEKLY"])
    active_instance = _recurring_provider_event(
        provider_event_id="synthetic-instance",
        etag='"instance-etag"',
        recurring_event_id="synthetic-provider-event",
        original_start=original,
    )
    writes.resolve_occurrence(
        intent.id,
        ResolveProviderOccurrenceInput(master=master_event, instance=active_instance),
    )
    assert (
        writes.record_result(
            intent.id,
            RecordProviderWriteResultInput(
                stage="patch",
                result_class="retryable_transport",
                safe_reason="synthetic_transport",
            ),
        ).state
        == "ambiguous"
    )
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ambiguous", executor_provenance="recovery"
        ),
    )
    writes.resolve_occurrence(
        intent.id,
        ResolveProviderOccurrenceInput(master=master_event, instance=active_instance),
    )
    retried = writes.reconcile_patch(
        intent.id,
        ReconcileProviderPatchInput(
            resolution_kind="identity_lookup", event=active_instance
        ),
    )
    assert retried.state == "retry_wait"
    assert retried.failure_reason == "ambiguous_patch_not_applied"


def test_bounded_recurring_create_persists_series_authority(tmp_path):
    _, calendar, writes, _ = _connected(tmp_path)
    intent = _create(writes, calendar, recurrence="weekdays")
    assert intent.recurrence_scope == "series"
    plan = next(
        item for item in writes.ready(ReadyWriteIntentsInput()) if item.id == intent.id
    )
    assert plan.changed_fields == ["title", "transparency", "temporal", "recurrence"]
    assert plan.desired_values.recurrence == ["RRULE:FREQ=WEEKLY;BYDAY=MO,TU,WE,TH,FR"]
    created = next(
        block
        for block in calendar.status().blocks
        if block.id == intent.calendar_block_id
    )
    assert created.recurrence_kind == "master"
    assert created.recurrence_preset == "weekdays"


def test_confirmation_gates_removal_not_ordinary_editing(tmp_path):
    """Every event synced from Google is `locked` Ion metadata, so gating edits
    on a confirmation would put a checkbox in front of essentially every real
    change. An edit is ETag-conditional and reversible, so it needs none.
    Deleting removes confirmed occurrences, so it keeps the explicit step."""
    engine, _, writes, block = _connected(tmp_path)
    with engine.begin() as connection:
        connection.execute(
            update(calendar_block_ion_metadata)
            .where(calendar_block_ion_metadata.c.calendar_block_id == block.id)
            .values(flexibility="locked")
        )
    assert _edit(writes, block, locked_confirmed=False).state == "ready"
    with pytest.raises(CalendarValidationError, match="locked_confirmation_required"):
        _delete(writes, block, locked_confirmed=False)


@pytest.mark.parametrize(
    ("access_role", "eligible"),
    [
        ("writer", True),
        ("owner", True),
        ("writerWithoutPrivateAccess", False),
        ("reader", False),
    ],
)
def test_only_writer_and_owner_roles_are_write_eligible(
    tmp_path, access_role, eligible
):
    _, calendar, writes, block = _connected(tmp_path, access_role=access_role)
    capability = calendar.status().blocks[0].provider_write_capability
    assert capability.eligible is eligible
    assert capability.reason == ("eligible" if eligible else "access_role_read_only")
    if eligible:
        assert _queue(writes, block).state == "ready"
    else:
        with pytest.raises(CalendarValidationError, match="access_role_read_only"):
            _queue(writes, block)


def test_intent_state_retry_restart_recovery_and_audit_are_durable(tmp_path):
    engine, _, writes, block = _connected(tmp_path)
    queued = _queue(writes, block)
    assert queued.state == "ready"
    assert _queue(writes, block, command_id=str(uuid4())).state == "queued"

    attempting = _transition(writes, queued, "attempting")
    assert attempting.attempt_count == 1
    retry = _transition(
        writes,
        attempting,
        "retry_wait",
        result="retryable_quota",
        next_attempt_at="2030-01-01T12:05:00Z",
    )
    restarted = CalendarWriteService(engine)
    before_due = restarted.recover(RecoverWriteIntentsInput(now="2030-01-01T12:04:59Z"))
    assert before_due.retry_wait_to_ready == 0
    # A write still waiting on its backoff reports when it becomes due, so the
    # dispatcher can wake itself once rather than stranding the write until the
    # user happens to trigger another Calendar action.
    assert before_due.next_retry_in_seconds == 1
    after_due = restarted.recover(RecoverWriteIntentsInput(now="2030-01-01T12:05:00Z"))
    assert after_due.retry_wait_to_ready == 1
    # Nothing is waiting once it has been promoted, so nothing is scheduled.
    assert after_due.next_retry_in_seconds is None
    ready = restarted.ready(ReadyWriteIntentsInput(now="2030-01-01T12:05:00Z"))
    assert [item.id for item in ready] == [retry.id]
    assert ready[0].provider_event_id == "synthetic-provider-event"
    assert ready[0].expected_provider_etag == '"synthetic-etag"'

    second_attempt = _transition(restarted, ready[0], "attempting")
    repaired = restarted.recover(RecoverWriteIntentsInput(now="2030-01-01T12:06:00Z"))
    assert repaired.attempting_to_ambiguous == 1
    foundation = restarted.foundation()
    ambiguous = next(
        item for item in foundation.pending if item.id == second_attempt.id
    )
    assert ambiguous.state == "ambiguous"
    assert ambiguous.failure_reason == "restart_after_attempt"

    with engine.connect() as connection:
        audits = connection.execute(
            select(calendar_provider_write_audit).where(
                calendar_provider_write_audit.c.intent_id == queued.id
            )
        ).all()
    serialized = json.dumps([row._asdict() for row in audits])
    assert "Synthetic event title" not in serialized
    assert "Synthetic revised title" not in serialized
    assert "@example.invalid" not in serialized
    assert "token" not in serialized.lower()


def test_invalid_transitions_attempt_ceiling_terminal_durability_and_pruning(tmp_path):
    engine, _, writes, block = _connected(tmp_path)
    intent = _queue(writes, block)
    with pytest.raises(CalendarValidationError, match="invalid"):
        _transition(writes, intent, "completed", result="success")

    current = intent
    for attempt in range(1, 6):
        current = _transition(writes, current, "attempting")
        assert current.attempt_count == attempt
        if attempt < 5:
            current = _transition(
                writes,
                current,
                "retry_wait",
                result="retryable_backend",
                next_attempt_at="2030-01-01T12:00:00Z",
            )
            writes.recover(RecoverWriteIntentsInput(now="2030-01-01T12:00:00Z"))
            current = next(
                item for item in writes.foundation().pending if item.id == intent.id
            )
    with pytest.raises(CalendarValidationError, match="final attempt"):
        _transition(
            writes,
            current,
            "retry_wait",
            result="retryable_backend",
            next_attempt_at="2030-01-01T12:05:00Z",
        )
    failed = _transition(
        writes, current, "failed", result="terminal_provider_rejection"
    )
    assert failed.state == "failed"
    assert any(item.id == failed.id for item in writes.foundation().pending)
    assert writes.prune(PruneWriteIntentsInput(now="2100-01-01T00:00:00Z")).pruned == 0

    second_engine, _, second_writes, second_block = _connected(tmp_path)
    completed = _transition(
        second_writes,
        _transition(second_writes, _queue(second_writes, second_block), "attempting"),
        "completed",
        result="success",
    )
    assert completed.resolved_at is not None
    assert (
        second_writes.prune(PruneWriteIntentsInput(now="2030-01-31T11:59:59Z")).pruned
        == 0
    )
    assert (
        second_writes.prune(PruneWriteIntentsInput(now="2030-01-31T12:00:00Z")).pruned
        == 1
    )
    with second_engine.connect() as connection:
        assert (
            connection.execute(
                select(calendar_provider_write_intents).where(
                    calendar_provider_write_intents.c.id == completed.id
                )
            ).one_or_none()
            is None
        )
        assert (
            connection.execute(
                select(calendar_provider_write_audit).where(
                    calendar_provider_write_audit.c.intent_id == completed.id
                )
            ).first()
            is not None
        )


@pytest.mark.parametrize(
    ("target", "result_class"),
    [
        ("conflict", "stale_precondition"),
        ("ambiguous", "retryable_transport"),
        ("reauth_required", "reauthentication_required"),
        ("failed", "terminal_provider_rejection"),
        ("cancelled", None),
    ],
)
def test_retention_prunes_only_completed_rows_and_keeps_audit_content_free(
    tmp_path, target, result_class
):
    """Accepted retention: only successfully completed operational rows are
    eligible. Unresolved, conflict, failed, ambiguous, reauthentication-blocked,
    and locally cancelled rows remain until explicitly resolved, and the
    durable audit never carries event content."""
    engine, _, writes, block = _connected(tmp_path)
    attempting = _transition(writes, _queue(writes, block), "attempting")
    if target == "cancelled":
        settled = _transition(
            writes,
            _transition(writes, attempting, "conflict", result="stale_precondition"),
            "cancelled",
        )
    else:
        settled = _transition(writes, attempting, target, result=result_class)
    assert settled.state == target

    # Far beyond any retention window: still never pruned.
    assert writes.prune(PruneWriteIntentsInput(now="2100-01-01T00:00:00Z")).pruned == 0
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(calendar_provider_write_intents).where(
                    calendar_provider_write_intents.c.id == settled.id
                )
            ).one_or_none()
            is not None
        )
        audit_rows = connection.execute(
            select(calendar_provider_write_audit).where(
                calendar_provider_write_audit.c.intent_id == settled.id
            )
        ).all()
    assert audit_rows
    serialized = " ".join(
        str(value) for row in audit_rows for value in row._mapping.values()
    )
    assert "Synthetic event title" not in serialized
    assert "Synthetic revised title" not in serialized


def test_bounded_lifecycle_soak_leaves_no_stranded_or_duplicated_state(tmp_path):
    """Bounded, deterministic Phase 2C-6 soak (not an open-ended fuzz): repeat
    the full synthetic write lifecycle and assert the invariants the audit
    cares about -- no permanently locked block, no orphaned intent state, no
    unbounded operational growth, no retry storm, no stale conflict
    projection, and no duplicate deterministic provider identity."""
    engine, calendar, writes, block = _connected(tmp_path)
    writes.random_fraction = lambda: 0.5
    rounds = 6
    seen_provider_ids: set[str] = set()

    for index in range(rounds):
        current = next(item for item in calendar.status().blocks if item.id == block.id)
        assert current.provider_write_capability.eligible is True, (
            f"round {index}: block became permanently locked"
        )
        intent = _edit(
            writes,
            current,
            command_id=str(uuid4()),
            title=f"Soak revision {index}",
        )
        writes.begin_attempt(
            intent.id,
            BeginWriteAttemptInput(
                expected_state="ready", executor_provenance="direct_human"
            ),
        )
        confirmed_etag = f'"soak-etag-{index}"'
        if index % 3 == 0:
            # Transient provider trouble, then a bounded retry that succeeds.
            retried = writes.record_result(
                intent.id,
                RecordProviderWriteResultInput(
                    stage="patch",
                    result_class="retryable_backend",
                    safe_reason="provider_backend_unavailable",
                ),
            )
            assert retried.state == "retry_wait"
            assert retried.attempt_count <= MAX_AUTOMATIC_ATTEMPTS
            writes.recover(RecoverWriteIntentsInput(now="2099-01-01T00:00:00Z"))
            writes.begin_attempt(
                intent.id,
                BeginWriteAttemptInput(
                    expected_state="ready", executor_provenance="recovery"
                ),
            )
        elif index % 3 == 1:
            # A real conflict: drift that survived the whole automatic rebase
            # budget, then resolved by keeping Google's version.
            conflicted = _exhaust_to_conflict(writes, intent)
            assert conflicted.state == "conflict"
            stale = next(
                item for item in calendar.status().blocks if item.id == block.id
            )
            assert stale.provider_write_state == "conflict"
            writes.keep_google_version(
                KeepGoogleVersionInput(
                    command_id=str(uuid4()),
                    calendar_block_id=block.id,
                    expected_block_revision=stale.revision,
                )
            )
            cleared = next(
                item for item in calendar.status().blocks if item.id == block.id
            )
            assert cleared.provider_write_state == "synced", (
                f"round {index}: resolved conflict still projects as needs-review"
            )
            continue

        completed = writes.reconcile_patch(
            intent.id,
            ReconcileProviderPatchInput(
                resolution_kind="patch_response",
                event=ProviderEventInput(
                    provider_event_id=block.provider_event_id,
                    provider_etag=confirmed_etag,
                    title=f"Soak revision {index}",
                    start=ProviderDateTime(
                        date_time="2030-01-01T09:00:00-08:00",
                        timezone="America/Los_Angeles",
                    ),
                    end=ProviderDateTime(
                        date_time="2030-01-01T10:00:00-08:00",
                        timezone="America/Los_Angeles",
                    ),
                ),
            ),
        )
        assert completed.state == "completed"
        settled = next(item for item in calendar.status().blocks if item.id == block.id)
        assert settled.title == f"Soak revision {index}"
        assert settled.provider_write_state == "synced"
        seen_provider_ids.add(settled.provider_event_id)

    # One canonical provider identity throughout -- no duplicate event.
    assert seen_provider_ids == {block.provider_event_id}

    # Restart mid-stream must not orphan or resurrect anything.
    restarted = CalendarWriteService(engine)
    repair = restarted.recover(RecoverWriteIntentsInput())
    assert repair.attempting_to_ambiguous == 0
    assert restarted.ready(ReadyWriteIntentsInput()) == []

    with engine.connect() as connection:
        states = (
            connection.execute(
                select(calendar_provider_write_intents.c.state).where(
                    calendar_provider_write_intents.c.calendar_block_id == block.id
                )
            )
            .scalars()
            .all()
        )
        blocks_for_event = connection.execute(
            select(func.count(google_event_links.c.calendar_block_id)).where(
                google_event_links.c.provider_event_id == block.provider_event_id
            )
        ).scalar_one()
    # Every operational row settled; nothing left mid-flight or in retry.
    assert set(states) <= {"completed", "cancelled"}, states
    assert len(states) == rounds
    assert blocks_for_event == 1

    final = next(item for item in calendar.status().blocks if item.id == block.id)
    assert final.provider_write_state == "synced"
    assert final.provider_write_capability.eligible is True
    assert final.provider_write_failure_class is None


def test_whole_series_change_confirms_the_master_and_leaves_exception_identity(
    tmp_path,
):
    """Canonical half of the first-occurrence defect: a confirmed whole-series
    time change must move the master itself, and must never rewrite an
    exception's immutable original-start identity. The renderer then decides
    whether a surviving exception is still anchored to the confirmed rule."""
    engine, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    original = ProviderDateTime(
        date_time="2030-01-01T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    master_event = _recurring_provider_event(recurrence=["RRULE:FREQ=WEEKLY"])

    # An earlier "This event" edit materializes an exception at 09:00.
    occurrence_intent = _edit(
        writes,
        master,
        recurrence_scope="occurrence",
        occurrence_original_start=original,
        title="Edited first occurrence",
    )
    writes.begin_attempt(
        occurrence_intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    instance = ProviderEventInput(
        provider_event_id="synthetic-instance",
        provider_etag='"instance-etag"',
        title="Edited first occurrence",
        status="confirmed",
        recurring_event_id="synthetic-provider-event",
        original_start=original,
        start=ProviderDateTime(
            date_time="2030-01-01T09:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
        end=ProviderDateTime(
            date_time="2030-01-01T10:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
    )
    writes.resolve_occurrence(
        occurrence_intent.id,
        ResolveProviderOccurrenceInput(master=master_event, instance=instance),
    )
    writes.reconcile_patch(
        occurrence_intent.id,
        ReconcileProviderPatchInput(resolution_kind="patch_response", event=instance),
    )

    # Now the owner moves the whole series to 11:00 and Google confirms it.
    current = next(item for item in calendar.status().blocks if item.id == master.id)
    series_intent = _edit(
        writes,
        current,
        command_id=str(uuid4()),
        recurrence_scope="series",
        edit_kind="edit",
        title=None,
        start_date="2030-01-01",
        start_time="11:00",
        end_date="2030-01-01",
        end_time="12:00",
        timezone="America/Los_Angeles",
        recurrence_risk_confirmed=True,
    )
    writes.begin_attempt(
        series_intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    moved_master = ProviderEventInput(
        provider_event_id="synthetic-provider-event",
        provider_etag='"master-v2"',
        title="Synthetic event title",
        status="confirmed",
        recurrence=["RRULE:FREQ=WEEKLY"],
        start=ProviderDateTime(
            date_time="2030-01-01T11:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
        end=ProviderDateTime(
            date_time="2030-01-01T12:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
    )
    assert (
        writes.reconcile_patch(
            series_intent.id,
            ReconcileProviderPatchInput(
                resolution_kind="patch_response", event=moved_master
            ),
        ).state
        == "completed"
    )

    blocks = calendar.status().blocks
    confirmed_master = next(item for item in blocks if item.id == master.id)
    exception = next(item for item in blocks if item.recurrence_kind == "exception")
    # The master carries the confirmed new series time.
    assert confirmed_master.start_at == "2030-01-01T11:00:00-08:00"
    assert confirmed_master.end_at == "2030-01-01T12:00:00-08:00"
    assert confirmed_master.provider_write_state == "synced"
    # The exception keeps its immutable identity and its own stale values; it is
    # the projection's job to stop treating it as an anchored override.
    assert exception.original_start_at == "2030-01-01T09:00:00-08:00"
    assert exception.start_at == "2030-01-01T09:00:00-08:00"

    # Restart preserves exactly the same canonical picture.
    restarted = CalendarService(engine)
    after = restarted.status().blocks
    assert next(item for item in after if item.id == master.id).start_at == (
        "2030-01-01T11:00:00-08:00"
    )
    assert (
        next(
            item for item in after if item.recurrence_kind == "exception"
        ).original_start_at
        == "2030-01-01T09:00:00-08:00"
    )


def test_bounded_recurrence_soak_keeps_occurrences_independent_and_unlocked(tmp_path):
    """Bounded recurrence-lifecycle soak: repeated occurrence edits and one
    occurrence cancellation must materialize exactly one exception per
    original start, never duplicate an occurrence identity, and never leave
    the master or a sibling occurrence permanently locked."""
    engine, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    master_event = _recurring_provider_event(recurrence=["RRULE:FREQ=WEEKLY"])
    originals = [
        ProviderDateTime(
            date_time=f"2030-01-{day:02d}T09:00:00-08:00",
            timezone="America/Los_Angeles",
        )
        for day in (8, 15, 22)
    ]

    for index, original in enumerate(originals):
        current = next(
            item for item in calendar.status().blocks if item.id == master.id
        )
        assert current.provider_write_capability.eligible is True, (
            f"round {index}: recurring master became permanently locked"
        )
        intent = _edit(
            writes,
            current,
            command_id=str(uuid4()),
            recurrence_scope="occurrence",
            occurrence_original_start=original,
            title=f"Occurrence {index}",
        )
        writes.begin_attempt(
            intent.id,
            BeginWriteAttemptInput(
                expected_state="ready", executor_provenance="direct_human"
            ),
        )
        instance = _recurring_provider_event(
            provider_event_id=f"synthetic-instance-{index}",
            etag=f'"instance-{index}-etag"',
            recurring_event_id="synthetic-provider-event",
            original_start=original,
        )
        writes.resolve_occurrence(
            intent.id,
            ResolveProviderOccurrenceInput(master=master_event, instance=instance),
        )
        completed = writes.reconcile_patch(
            intent.id,
            ReconcileProviderPatchInput(
                resolution_kind="patch_response",
                event=instance.model_copy(
                    update={
                        "provider_etag": f'"instance-{index}-etag-2"',
                        "title": f"Occurrence {index}",
                    }
                ),
            ),
        )
        assert completed.state == "completed"

    blocks = calendar.status().blocks
    exceptions = [item for item in blocks if item.recurrence_kind == "exception"]
    # Exactly one materialized exception per distinct original start.
    assert len(exceptions) == len(originals)
    assert len({item.provider_event_id for item in exceptions}) == len(originals)
    assert sorted(item.title for item in exceptions) == [
        "Occurrence 0",
        "Occurrence 1",
        "Occurrence 2",
    ]
    # Every materialized sibling stays independently writable.
    for item in exceptions:
        assert item.provider_write_state == "synced"
        assert item.provider_write_capability.eligible is True

    # Cancelling one occurrence must not lock the others or the master.
    # Select by identity, not list position: the synthetic instances share a
    # start time, so projection order is not a stable selector.
    target = next(item for item in exceptions if item.title == "Occurrence 0")
    cancel = _delete(
        writes,
        target,
        command_id=str(uuid4()),
        recurrence_scope="occurrence",
        occurrence_original_start=originals[0],
    )
    assert cancel.operation == "cancel_occurrence"
    writes.begin_attempt(
        cancel.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    cancelled_instance = _recurring_provider_event(
        provider_event_id="synthetic-instance-0",
        etag='"instance-0-etag-2"',
        recurring_event_id="synthetic-provider-event",
        original_start=originals[0],
    )
    writes.resolve_occurrence(
        cancel.id,
        ResolveProviderOccurrenceInput(
            master=master_event, instance=cancelled_instance
        ),
    )
    writes.reconcile_patch(
        cancel.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=cancelled_instance.model_copy(
                update={
                    "provider_etag": '"instance-0-cancelled"',
                    "status": "cancelled",
                }
            ),
        ),
    )

    after = calendar.status().blocks
    survivors = [
        item
        for item in after
        if item.recurrence_kind == "exception" and item.id != target.id
    ]
    assert len(survivors) == len(originals) - 1
    for item in survivors:
        assert item.provider_write_capability.eligible is True, (
            "an unrelated occurrence was locked by a sibling cancellation"
        )
    assert (
        next(
            item for item in after if item.id == master.id
        ).provider_write_capability.eligible
        is True
    )
    with engine.connect() as connection:
        links = connection.execute(
            select(func.count(google_event_links.c.calendar_block_id))
        ).scalar_one()
    # Master plus one link per materialized occurrence -- nothing duplicated.
    assert links == len(originals) + 1


def test_local_first_title_edit_overlays_confirmed_base_and_reconciles_patch(tmp_path):
    engine, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block)
    assert intent.state == "ready"
    projected = calendar.status().blocks[0]
    assert projected.title == "Synthetic revised title"
    assert projected.provider_write_state == "pending"
    assert projected.provider_write_detail == "ready"
    # Unsettled provider work never removes the owner's ability to act again.
    assert projected.provider_write_capability.reason == "eligible"

    plan = writes.ready(ReadyWriteIntentsInput())[0]
    assert plan.changed_fields == ["title"]
    assert plan.base_values == ProviderWriteValues(title="Synthetic event title")
    assert plan.desired_values == ProviderWriteValues(title="Synthetic revised title")
    assert plan.expected_provider_etag == '"synthetic-etag"'
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(calendar_blocks.c.title).where(calendar_blocks.c.id == block.id)
            ).scalar_one()
            == "Synthetic event title"
        )

    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    completed = writes.reconcile_patch(
        intent.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=ProviderEventInput(
                provider_event_id="synthetic-provider-event",
                provider_etag='"synthetic-etag-v2"',
                title="Synthetic revised title",
                start=ProviderDateTime(
                    date_time="2030-01-01T09:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
                end=ProviderDateTime(
                    date_time="2030-01-01T10:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
            ),
        ),
    )
    assert completed.state == "completed"
    confirmed = calendar.status().blocks[0]
    assert confirmed.title == "Synthetic revised title"
    assert confirmed.provider_write_state == "synced"
    assert confirmed.provider_write_detail == "confirmed"
    assert confirmed.provider_write_overlay is None
    with engine.connect() as connection:
        canonical_actions = (
            connection.execute(
                select(audit_events.c.action).where(
                    audit_events.c.entity_id == block.id
                )
            )
            .scalars()
            .all()
        )
        compact = connection.execute(
            select(calendar_provider_write_audit).where(
                calendar_provider_write_audit.c.intent_id == intent.id
            )
        ).all()
    assert "edit_requested" in canonical_actions
    assert "provider_patch_confirmed" in canonical_actions
    assert [row.action for row in compact] == [
        "write_intent_queued",
        "write_intent_ready",
        "write_attempt_started",
        "write_completed",
    ]
    assert "Synthetic revised title" not in json.dumps(
        [row._asdict() for row in compact]
    )


def test_timed_edit_move_and_resize_normalize_only_changed_fields(tmp_path):
    _, calendar, writes, block = _connected(tmp_path)
    edited = _edit(
        writes,
        block,
        title="Synthetic event title",
        start_date="2030-01-01",
        end_date="2030-01-01",
        start_time="10:00",
        end_time="11:30",
        timezone="America/Los_Angeles",
    )
    edit_plan = writes.ready(ReadyWriteIntentsInput())[0]
    assert edit_plan.id == edited.id
    assert edit_plan.changed_fields == ["temporal"]
    assert edit_plan.desired_values.start == ProviderDateTime(
        date_time="2030-01-01T10:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    assert edit_plan.desired_values.end == ProviderDateTime(
        date_time="2030-01-01T11:30:00-08:00",
        timezone="America/Los_Angeles",
    )

    second_engine, _, second_writes, second_block = _connected(tmp_path)
    moved = _edit(
        second_writes,
        second_block,
        edit_kind="move",
        title=None,
        start_date="2030-01-02",
        start_time="13:15",
        timezone="America/Los_Angeles",
    )
    move_plan = second_writes.ready(ReadyWriteIntentsInput())[0]
    assert move_plan.id == moved.id
    assert move_plan.desired_values.start.date_time == "2030-01-02T13:15:00-08:00"
    assert move_plan.desired_values.end.date_time == "2030-01-02T14:15:00-08:00"
    with second_engine.connect() as connection:
        assert (
            "move_requested"
            in connection.execute(
                select(audit_events.c.action).where(
                    audit_events.c.entity_id == second_block.id
                )
            )
            .scalars()
            .all()
        )

    _, _, third_writes, third_block = _connected(tmp_path)
    resized = _edit(
        third_writes,
        third_block,
        edit_kind="resize",
        title=None,
        end_date="2030-01-01",
        end_time="11:45",
        timezone="America/Los_Angeles",
    )
    resize_plan = third_writes.ready(ReadyWriteIntentsInput())[0]
    assert resize_plan.id == resized.id
    assert resize_plan.desired_values.end.date_time == "2030-01-01T11:45:00-08:00"


def test_edit_rejects_invalid_duration_dst_timezone_conversion_and_unconfirmed_etag(
    tmp_path,
):
    engine, _, writes, block = _connected(tmp_path)
    with pytest.raises(CalendarValidationError, match="after start"):
        _edit(
            writes,
            block,
            title="Synthetic event title",
            start_date="2030-01-01",
            end_date="2030-01-01",
            start_time="10:00",
            end_time="09:00",
            timezone="America/Los_Angeles",
        )
    with pytest.raises(CalendarValidationError, match="skipped DST"):
        _edit(
            writes,
            block,
            title="Synthetic event title",
            start_date="2030-03-10",
            end_date="2030-03-10",
            start_time="02:15",
            end_time="03:15",
            timezone="America/Los_Angeles",
        )
    with pytest.raises(CalendarValidationError, match="ambiguous"):
        _edit(
            writes,
            block,
            title="Synthetic event title",
            start_date="2030-11-03",
            end_date="2030-11-03",
            start_time="01:15",
            end_time="02:15",
            timezone="America/Los_Angeles",
        )
    with pytest.raises(CalendarValidationError, match="timezone_change_unsupported"):
        _edit(
            writes,
            block,
            title="Synthetic event title",
            start_date="2030-01-01",
            end_date="2030-01-01",
            start_time="10:00",
            end_time="11:00",
            timezone="UTC",
        )
    with engine.begin() as connection:
        connection.execute(update(google_event_links).values(provider_etag="*"))
    assert _connected  # keep the synthetic fixture visibly local-only
    with pytest.raises(CalendarValidationError, match="provider_unconfirmed"):
        _edit(writes, block)


def test_all_day_edit_preserves_civil_end_exclusive_dates(tmp_path):
    _, calendar, writes, block = _connected(
        tmp_path,
        event_overrides={
            "start": ProviderDateTime(date="2030-02-14"),
            "end": ProviderDateTime(date="2030-02-15"),
        },
    )
    intent = _edit(
        writes,
        block,
        title="Synthetic all-day revised",
        start_date="2030-02-15",
        end_date="2030-02-17",
    )
    plan = writes.ready(ReadyWriteIntentsInput())[0]
    assert plan.id == intent.id
    assert plan.desired_values.start == ProviderDateTime(date="2030-02-15")
    assert plan.desired_values.end == ProviderDateTime(date="2030-02-17")
    projected = calendar.status().blocks[0]
    assert projected.start_date == "2030-02-15"
    assert projected.end_date == "2030-02-17"
    assert projected.start_at is None


@pytest.mark.parametrize(
    ("result_class", "expected_state"),
    [
        ("reauthentication_required", "reauth_required"),
        ("terminal_provider_rejection", "failed"),
        ("provider_not_found", "conflict"),
        ("stale_precondition", "ambiguous"),
        ("retryable_quota", "retry_wait"),
        ("retryable_backend", "retry_wait"),
    ],
)
def test_patch_failure_classes_are_durable_and_conflicts_do_not_retry(
    tmp_path, result_class, expected_state
):
    _, _, writes, block = _connected(tmp_path)
    writes.random_fraction = lambda: 0.5
    intent = _edit(writes, block)
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    result = writes.record_result(
        intent.id,
        RecordProviderWriteResultInput(
            stage="patch",
            result_class=result_class,
            safe_reason="synthetic_safe_reason",
        ),
    )
    assert result.state == expected_state
    if expected_state == "retry_wait":
        assert result.next_attempt_at is not None
    else:
        assert result.next_attempt_at is None


@pytest.mark.parametrize(
    ("result_class", "expected_state"),
    [
        ("reauthentication_required", "reauth_required"),
        ("terminal_provider_rejection", "failed"),
        ("provider_not_found", "conflict"),
        ("retryable_quota", "retry_wait"),
        ("retryable_backend", "retry_wait"),
    ],
)
def test_provider_failure_class_surfaces_distinctly_to_the_renderer_dto(
    tmp_path, result_class, expected_state
):
    """The audit found the renderer could only ever see the coarse
    provider_write_state/provider_write_detail bucket, collapsing distinct
    failures (e.g. quota vs. backend retry, or provider_not_found vs.
    stale_precondition conflict) into one generic renderer-visible value.
    provider_write_failure_class/_reason must expose the real distinction."""
    _, calendar, writes, block = _connected(tmp_path)
    writes.random_fraction = lambda: 0.5
    intent = _edit(writes, block)
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    result = writes.record_result(
        intent.id,
        RecordProviderWriteResultInput(
            stage="patch",
            result_class=result_class,
            safe_reason="synthetic_safe_reason",
        ),
    )
    assert result.state == expected_state

    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.provider_write_failure_class == result_class
    assert projected.provider_write_failure_reason == "synthetic_safe_reason"


def test_completed_write_never_surfaces_a_stale_failure_class(tmp_path):
    """A row that eventually succeeds after an earlier retryable failure
    must not keep showing that failure's class once `completed`."""
    _, calendar, writes, block = _connected(tmp_path)
    intent = _queue(writes, block)
    attempting = _transition(writes, intent, "attempting")
    retry_wait = _transition(
        writes,
        attempting,
        "retry_wait",
        result="retryable_backend",
        next_attempt_at="2030-01-01T12:00:00Z",
    )
    assert retry_wait.failure_class == "retryable_backend"
    ready_again = _transition(writes, retry_wait, "ready")
    attempting_again = _transition(writes, ready_again, "attempting")
    completed = _transition(writes, attempting_again, "completed", result="success")
    assert completed.state == "completed"

    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.provider_write_state == "synced"
    assert projected.provider_write_failure_class is None
    assert projected.provider_write_failure_reason is None


def test_reconnect_recovery_repairs_then_rebases_onto_drift(tmp_path):
    """Phase 2C-6 ordering: recover durable intents -> detect provider drift
    -> conflict explicitly, never blind-dispatch a stale write, and never lose
    the human's preserved intent across the restart."""
    engine, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block, title="Renamed before the crash")
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )

    # Restart. A persisted `attempting` row is not dispatchable until it has
    # been repaired, so recovery genuinely precedes dispatch selection.
    restarted = CalendarWriteService(engine)
    assert restarted.ready(ReadyWriteIntentsInput()) == []
    repair = restarted.recover(RecoverWriteIntentsInput())
    assert repair.attempting_to_ambiguous == 1

    # The human's durable intent survived the crash and is reconcilable.
    recovered = restarted.ready(ReadyWriteIntentsInput())
    assert [plan.id for plan in recovered] == [intent.id]
    assert recovered[0].state == "ambiguous"
    assert recovered[0].desired_values.title == "Renamed before the crash"

    # Google moved on while Ion was down. Drift is still detected before any
    # provider mutation -- but it is absorbed, not escalated: the recovered
    # intent re-aims at the freshly confirmed ETag and carries on.
    with engine.begin() as connection:
        connection.execute(
            update(google_event_links)
            .where(google_event_links.c.calendar_block_id == block.id)
            .values(provider_etag='"moved-on-while-ion-was-down"')
        )
    resumed = restarted.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ambiguous", executor_provenance="recovery"
        ),
    )
    assert resumed.state == "attempting"
    with engine.connect() as connection:
        rearmed = connection.execute(
            select(calendar_provider_write_intents.c.expected_provider_etag).where(
                calendar_provider_write_intents.c.id == intent.id
            )
        ).scalar_one()
    assert rearmed == '"moved-on-while-ion-was-down"'
    assert rearmed != "*"

    # Nothing is stranded and nothing is escalated: the write is simply still
    # in flight, and the human's preserved value is still what the Calendar
    # shows while it settles.
    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.provider_write_state == "pending"
    assert projected.provider_write_failure_class is None
    assert projected.provider_write_overlay.title == "Renamed before the crash"


def test_reauthentication_preserves_pending_writes_until_consent_returns(tmp_path):
    """Phase 2C-6 capability change: losing write scope after an intent was
    created must block the write safely, keep it durable, and let recovery
    resume it once the owner re-consents -- with no unauthorized dispatch and
    no retry storm in between."""
    engine, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block, title="Queued before scope loss")
    with engine.begin() as connection:
        connection.execute(
            update(google_accounts).values(calendar_write_scope_state="reauth_required")
        )

    blocked = writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(expected_state="ready", executor_provenance="recovery"),
    )
    assert blocked.state == "reauth_required"
    assert blocked.failure_class == "reauthentication_required"
    # Not dispatchable while unauthorized, and not silently discarded.
    assert writes.ready(ReadyWriteIntentsInput()) == []
    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.provider_write_detail == "reauth_required"
    assert projected.provider_write_failure_class == "reauthentication_required"

    # Re-consent returns; recovery resumes the already-authorized human intent.
    with engine.begin() as connection:
        connection.execute(
            update(google_accounts).values(calendar_write_scope_state="write_granted")
        )
    assert writes.recover(RecoverWriteIntentsInput()).reauth_required_to_ready == 1
    resumed = writes.ready(ReadyWriteIntentsInput())
    assert [plan.id for plan in resumed] == [intent.id]
    assert resumed[0].desired_values.title == "Queued before scope loss"


def test_capability_loss_fails_safely_without_unauthorized_dispatch(tmp_path):
    """Phase 2C-6 capability change: a calendar downgraded to reader after the
    intent was created must stop terminally with a safe reason rather than
    retrying forever or writing without authority."""
    engine, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block, title="Queued before access-role change")
    with engine.begin() as connection:
        connection.execute(update(google_calendars).values(access_role="reader"))

    blocked = writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(expected_state="ready", executor_provenance="recovery"),
    )
    assert blocked.state == "failed"
    assert blocked.failure_reason == "access_role_read_only"
    assert blocked.failure_class == "terminal_provider_rejection"
    # No infinite retry: a terminal failure is never re-selected for dispatch.
    assert writes.ready(ReadyWriteIntentsInput()) == []
    assert writes.recover(RecoverWriteIntentsInput()).retry_wait_to_ready == 0

    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.provider_write_state == "failed"
    assert projected.provider_write_failure_class == "terminal_provider_rejection"

    # The durable intent is preserved, and the human still has an exit so the
    # block does not stay locked forever once capability returns.
    with engine.begin() as connection:
        connection.execute(update(google_calendars).values(access_role="owner"))
    current = next(item for item in calendar.status().blocks if item.id == block.id)
    writes.keep_google_version(
        KeepGoogleVersionInput(
            command_id=str(uuid4()),
            calendar_block_id=block.id,
            expected_block_revision=current.revision,
        )
    )
    released = next(item for item in calendar.status().blocks if item.id == block.id)
    assert released.provider_write_state == "synced"
    assert released.provider_write_capability.eligible is True


def test_offline_restart_and_ambiguous_patch_lookup_preserve_intent(tmp_path):
    engine, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block)
    restarted = CalendarWriteService(engine)
    assert restarted.ready(ReadyWriteIntentsInput())[0].id == intent.id
    restarted.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(expected_state="ready", executor_provenance="recovery"),
    )
    assert restarted.recover(RecoverWriteIntentsInput()).attempting_to_ambiguous == 1
    ambiguous = restarted.ready(ReadyWriteIntentsInput())[0]
    assert ambiguous.state == "ambiguous"
    restarted.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ambiguous", executor_provenance="recovery"
        ),
    )
    completed = restarted.reconcile_patch(
        intent.id,
        ReconcileProviderPatchInput(
            resolution_kind="identity_lookup",
            event=ProviderEventInput(
                provider_event_id="synthetic-provider-event",
                provider_etag='"synthetic-etag-v2"',
                title="Synthetic revised title",
                start=ProviderDateTime(
                    date_time="2030-01-01T09:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
                end=ProviderDateTime(
                    date_time="2030-01-01T10:00:00-08:00",
                    timezone="America/Los_Angeles",
                ),
            ),
        ),
    )
    assert completed.state == "completed"
    assert calendar.status().blocks[0].provider_write_state == "synced"


def test_provider_refresh_rebases_a_pending_intent_instead_of_conflicting(tmp_path):
    """A background refresh that finds newer provider state re-aims the pending
    write at it. The user's intent is preserved and still projected; it does not
    become a review task merely because Google's ETag moved."""
    engine, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block)
    calendar_id = calendar.status().calendars[0].id
    generation = str(uuid4())
    calendar.begin_sync(
        calendar_id, SyncBeginInput(generation=generation, mode="incremental")
    )
    calendar.apply_sync_page(
        calendar_id,
        SyncPageInput(
            generation=generation,
            events=[
                ProviderEventInput(
                    provider_event_id="synthetic-provider-event",
                    provider_etag='"synthetic-etag-v2"',
                    title="Synthetic provider-side title",
                    start=ProviderDateTime(
                        date_time="2030-01-01T09:00:00-08:00",
                        timezone="America/Los_Angeles",
                    ),
                    end=ProviderDateTime(
                        date_time="2030-01-01T10:00:00-08:00",
                        timezone="America/Los_Angeles",
                    ),
                )
            ],
        ),
    )
    status = calendar.status().blocks[0]
    # The Calendar keeps showing what the user asked for while it settles.
    assert status.title == "Synthetic revised title"
    assert status.provider_write_state == "pending"
    assert status.provider_write_overlay.title == "Synthetic revised title"
    with engine.connect() as connection:
        # Google's confirmed value is adopted underneath the pending overlay.
        assert (
            connection.execute(
                select(calendar_blocks.c.title).where(calendar_blocks.c.id == block.id)
            ).scalar_one()
            == "Synthetic provider-side title"
        )
        stored = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.id == intent.id
            )
        ).one()
    assert json.loads(stored.desired_values_json)["title"] == "Synthetic revised title"
    assert stored.state == "ready"
    # Re-aimed at the freshly confirmed ETag, never a wildcard.
    assert stored.expected_provider_etag == '"synthetic-etag-v2"'


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("calendar_read_only", "access_role_read_only"),
        ("calendar_deleted", "calendar_deleted"),
        ("account_read_only", "account_read_only"),
    ],
)
def test_patch_dispatch_rechecks_capability_loss(tmp_path, mutation, reason):
    engine, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block)
    with engine.begin() as connection:
        if mutation == "calendar_read_only":
            connection.execute(update(google_calendars).values(access_role="reader"))
        elif mutation == "calendar_deleted":
            connection.execute(
                update(google_calendars).values(
                    provider_deleted=True, enabled_in_ion=False
                )
            )
        else:
            connection.execute(
                update(google_accounts).values(calendar_write_scope_state="read_only")
            )
    blocked = writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(expected_state="ready", executor_provenance="recovery"),
    )
    assert blocked.state == "failed"
    assert blocked.failure_reason == reason
    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.provider_write_state == "failed"
    assert projected.provider_write_capability.reason == reason


def test_fixed_local_write_routes_are_authenticated_bounded_and_content_safe(tmp_path):
    token = "synthetic-session-token"
    headers = {"X-Ion-Session": token}
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    with TestClient(create_production_app(settings, token)) as client:
        assert client.get("/v1/calendar/write-foundation").status_code == 401
        connected = client.post(
            "/v1/calendar/accounts/connect",
            headers=headers,
            json={
                "provider_account_id": "synthetic@example.invalid",
                "display_name": "Synthetic Account",
                "granted_scopes": [CALENDAR_LIST_SCOPE, EVENTS_WRITE_SCOPE],
                "keychain_locator": "synthetic-keychain-locator",
                "calendars": [
                    {
                        "provider_calendar_id": "calendar@example.invalid",
                        "summary": "Synthetic Calendar",
                        "timezone": "UTC",
                        "access_role": "owner",
                        "is_primary": True,
                        "provider_selected": True,
                    }
                ],
            },
        ).json()
        calendar_id = connected["calendars"][0]["id"]
        generation = str(uuid4())
        assert (
            client.post(
                f"/v1/calendar/calendars/{calendar_id}/sync/begin",
                headers=headers,
                json={"generation": generation, "mode": "full"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/v1/calendar/calendars/{calendar_id}/sync/page",
                headers=headers,
                json={
                    "generation": generation,
                    "events": [
                        {
                            "provider_event_id": "synthetic-event",
                            "provider_etag": '"synthetic-etag"',
                            "title": "Synthetic private event title",
                            "start": {
                                "date_time": "2030-01-01T09:00:00Z",
                                "timezone": "UTC",
                            },
                            "end": {
                                "date_time": "2030-01-01T10:00:00Z",
                                "timezone": "UTC",
                            },
                        }
                    ],
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"/v1/calendar/calendars/{calendar_id}/sync/complete",
                headers=headers,
                json={"generation": generation, "next_sync_token": "synthetic-sync"},
            ).status_code
            == 200
        )
        status = client.get("/v1/calendar/status", headers=headers).json()
        block = status["blocks"][0]
        queued = client.post(
            "/v1/calendar/internal/write-intents",
            headers=headers,
            json={
                "command_id": str(uuid4()),
                "calendar_block_id": block["id"],
                "operation": "patch",
                "recurrence_scope": "single",
                "changed_fields": ["title"],
                "base_values": {"title": "Synthetic private event title"},
                "desired_values": {"title": "Synthetic private revised title"},
                "expected_block_revision": block["revision"],
                "provenance": "direct_human",
            },
        )
        assert queued.status_code == 200
        serialized = client.post(
            "/v1/calendar/internal/write-intents/edit",
            headers=headers,
            json={
                "command_id": str(uuid4()),
                "calendar_block_id": block["id"],
                "edit_kind": "edit",
                "expected_block_revision": block["revision"],
                "title": "Synthetic later revision",
                "recurrence_scope": "single",
                "locked_confirmed": True,
                "provenance": "direct_human",
            },
        )
        # Provider dispatch stays serialized, but the owner is never told they
        # cannot edit yet: a second direct-human mutation is accepted durably.
        assert serialized.status_code == 200
        assert serialized.json()["intent"]["state"] in ("ready", "queued")
        foundation = client.get("/v1/calendar/write-foundation", headers=headers)
        assert foundation.status_code == 200
        assert foundation.json()["blocks"][0] == {
            "calendar_block_id": block["id"],
            "eligible": False,
            "reason": "write_pending",
        }
        for forbidden in [
            "Synthetic private event title",
            "Synthetic private revised title",
            "synthetic-event",
            "synthetic-etag",
            "keychain",
            "token",
        ]:
            assert forbidden not in foundation.text
        ready = client.post(
            "/v1/calendar/internal/write-intents/ready",
            headers=headers,
            json={"now": "2030-01-01T00:00:00Z", "limit": 1000},
        )
        assert ready.status_code == 422
        assert "provider_event_id" not in ready.text


def _google_event(**overrides):
    """The synthetic provider event as Google would return it on a re-read."""
    values = {
        "provider_event_id": "synthetic-provider-event",
        "provider_etag": '"synthetic-etag"',
        "title": "Synthetic event title",
        "location": None,
        "start": ProviderDateTime(
            date_time="2030-01-01T09:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
        "end": ProviderDateTime(
            date_time="2030-01-01T10:00:00-08:00",
            timezone="America/Los_Angeles",
        ),
    }
    values.update(overrides)
    return ProviderEventInput(**values)


def _drift_then_reread(writes, intent, event, *, expected_state=None):
    """One full automatic convergence cycle, exactly as the dispatcher drives it.

    attempt -> Google reports the precondition stale -> Ion re-reads confirmed
    provider state -> the pending intent rebases onto it. No human step.
    """
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state=expected_state or intent.state,
            executor_provenance="direct_human",
        ),
    )
    ambiguous = writes.record_result(
        intent.id,
        RecordProviderWriteResultInput(
            stage="patch",
            result_class="stale_precondition",
            safe_reason="provider_values_changed",
        ),
    )
    assert ambiguous.state == "ambiguous", "ordinary drift must not stop for review"
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ambiguous", executor_provenance="recovery"
        ),
    )
    return writes.reconcile_patch(
        intent.id,
        ReconcileProviderPatchInput(
            resolution_kind="identity_lookup",
            event=event,
        ),
    )


def test_drift_on_a_different_field_converges_automatically(tmp_path):
    """A: Ion changed the title, Google independently changed the location.

    Both survive with no human step. Nothing merges them explicitly -- the
    provider body carries only Ion's changed field, so Google's untouched
    fields are never overwritten.
    """
    _, calendar, writes, block = _connected(tmp_path)
    intent = _queue(writes, block)

    rebased = _drift_then_reread(
        writes,
        intent,
        _google_event(provider_etag='"google-moved-on"', location="Room Y"),
    )

    # Automatically re-armed against Google's fresh ETag -- not conflicted,
    # and never against a wildcard.
    assert rebased.state == "ready"
    plan = writes.ready(ReadyWriteIntentsInput())[0]
    assert plan.expected_provider_etag == '"google-moved-on"', (
        "the retry must carry Google's fresh ETag, never the stale one"
    )
    assert plan.expected_provider_etag != "*"

    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.provider_write_state == "pending"
    assert projected.location == "Room Y", "Google's own change must survive"
    assert projected.provider_write_overlay.title == "Synthetic revised title", (
        "the user's pending change must still be what the Calendar shows"
    )

    # The retry then confirms and settles, with Google's field intact.
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(expected_state="ready", executor_provenance="recovery"),
    )
    completed = writes.reconcile_patch(
        intent.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=_google_event(
                provider_etag='"settled"',
                title="Synthetic revised title",
                location="Room Y",
            ),
        ),
    )
    assert completed.state == "completed"
    settled = next(item for item in calendar.status().blocks if item.id == block.id)
    assert settled.title == "Synthetic revised title"
    assert settled.location == "Room Y"
    assert settled.provider_write_state == "synced"


def test_same_field_drift_settles_the_pending_intent_then_yields_to_google(tmp_path):
    """B: both sides changed the same field while an Ion write was pending.

    The pending direct-human value wins that settlement cycle. This is not
    Ion-always-wins: once the intent confirms, the special ownership ends and
    the next Google change is adopted normally.
    """
    _, calendar, writes, block = _connected(tmp_path)
    intent = _queue(writes, block)

    rebased = _drift_then_reread(
        writes,
        intent,
        _google_event(
            provider_etag='"google-renamed"', title="Renamed in Google instead"
        ),
    )
    assert rebased.state == "ready"

    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.provider_write_overlay.title == "Synthetic revised title", (
        "the pending direct-human value owns its own field until it settles"
    )

    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(expected_state="ready", executor_provenance="recovery"),
    )
    completed = writes.reconcile_patch(
        intent.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=_google_event(
                provider_etag='"ion-won"', title="Synthetic revised title"
            ),
        ),
    )
    assert completed.state == "completed"

    # Ownership ends at confirmation: a later Google edit now flows into Ion.
    calendar_id = calendar.status().calendars[0].id
    generation = str(uuid4())
    calendar.begin_sync(calendar_id, SyncBeginInput(generation=generation, mode="full"))
    calendar.apply_sync_page(
        calendar_id,
        SyncPageInput(
            generation=generation,
            events=[
                _google_event(
                    provider_etag='"google-latest"', title="Google decided later"
                )
            ],
        ),
    )
    calendar.complete_sync(
        calendar_id,
        SyncCompleteInput(generation=generation, next_sync_token="synthetic-sync-2"),
    )
    latest = next(item for item in calendar.status().blocks if item.id == block.id)
    assert latest.title == "Google decided later"
    assert latest.provider_write_state == "synced"
    assert latest.provider_write_overlay is None


def test_read_sync_during_a_pending_intent_creates_no_conflict(tmp_path):
    """C: incremental Google sync lands before the Ion write confirms.

    Untouched Google fields update; the pending Ion field keeps projecting the
    user's intent; nothing becomes "needs review".
    """
    _, calendar, writes, block = _connected(tmp_path)
    intent = _queue(writes, block)
    assert intent.state == "ready"

    calendar_id = calendar.status().calendars[0].id
    generation = str(uuid4())
    calendar.begin_sync(calendar_id, SyncBeginInput(generation=generation, mode="full"))
    calendar.apply_sync_page(
        calendar_id,
        SyncPageInput(
            generation=generation,
            events=[_google_event(provider_etag='"mid-flight"', location="Room Z")],
        ),
    )
    calendar.complete_sync(
        calendar_id,
        SyncCompleteInput(generation=generation, next_sync_token="synthetic-sync-2"),
    )

    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.location == "Room Z"
    assert projected.provider_write_state == "pending"
    assert projected.provider_write_state != "conflict"
    assert projected.provider_write_overlay.title == "Synthetic revised title"


def test_repeated_provider_revisions_converge_within_the_attempt_budget(tmp_path):
    """D: Google keeps moving. Ion keeps rebasing, without ever asking."""
    _, calendar, writes, block = _connected(tmp_path)
    intent = _queue(writes, block)

    state = intent
    for revision in range(2):
        rebased = _drift_then_reread(
            writes,
            state,
            _google_event(provider_etag=f'"revision-{revision}"'),
            expected_state=state.state,
        )
        assert rebased.state == "ready"
        plan = writes.ready(ReadyWriteIntentsInput())[0]
        assert plan.expected_provider_etag == f'"revision-{revision}"'
        projected = next(
            item for item in calendar.status().blocks if item.id == block.id
        )
        assert projected.provider_write_state == "pending", (
            "repeated drift must never surface as a conflict"
        )
        state = rebased

    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(expected_state="ready", executor_provenance="recovery"),
    )
    completed = writes.reconcile_patch(
        intent.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=_google_event(
                provider_etag='"final"', title="Synthetic revised title"
            ),
        ),
    )
    assert completed.state == "completed"


def test_drift_that_outlasts_the_budget_becomes_an_honest_conflict(tmp_path):
    """The rebase is bounded. Exhausting it is the truthful signal that this is
    not ordinary drift, and only then does a human decide."""
    _, calendar, writes, block = _connected(tmp_path)
    intent = _queue(writes, block)
    conflicted = _exhaust_to_conflict(writes, intent)
    assert conflicted.state == "conflict"
    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.provider_write_state == "conflict"


def test_provider_deletion_during_a_pending_edit_is_not_rebased_away(tmp_path):
    """I: there is no target left to rebase onto, so this stays exceptional and
    is never silently recreated."""
    _, calendar, writes, block = _connected(tmp_path)
    intent = _queue(writes, block)
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    result = writes.record_result(
        intent.id,
        RecordProviderWriteResultInput(
            stage="patch",
            result_class="provider_not_found",
            safe_reason="provider_deleted",
        ),
    )
    assert result.state == "conflict"
    assert result.failure_class == "provider_not_found"


def test_series_edit_drift_rebases_automatically(tmp_path):
    """F: All events. Master ETag moved; Ion re-aims and retries by itself."""
    _, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=DAILY"]}
    )
    intent = _edit(
        writes,
        master,
        recurrence_scope="series",
        title="Renamed whole series",
    )
    rebased = _drift_then_reread(
        writes,
        intent,
        _recurring_provider_event(
            etag='"series-moved"', recurrence=["RRULE:FREQ=DAILY"]
        ),
    )
    assert rebased.state == "ready"
    assert writes.ready(ReadyWriteIntentsInput())[0].expected_provider_etag == (
        '"series-moved"'
    )
    projected = next(
        item for item in calendar.status().blocks if item.recurrence_kind == "master"
    )
    assert projected.provider_write_state == "pending"


def test_split_trim_drift_rebases_without_restarting_the_split(tmp_path):
    """G: drift on the old master before its trim confirms rebases in place.

    The split must not restart: the queued future master keeps its deterministic
    identity and stays chained behind the same trim, so a rebase can never
    produce a duplicate future series.
    """
    engine, _, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    original = ProviderDateTime(
        date_time="2030-01-15T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    trim = _split_edit(writes, master, original)

    with engine.connect() as connection:
        dependent_before = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.predecessor_intent_id == trim.id
            )
        ).one()

    rebased = _drift_then_reread(
        writes,
        trim,
        _recurring_provider_event(
            etag='"master-moved"', recurrence=["RRULE:FREQ=WEEKLY"]
        ),
    )
    assert rebased.state == "ready"
    assert rebased.id == trim.id, "a rebase re-arms the trim, it does not replace it"

    with engine.connect() as connection:
        dependent_after = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.predecessor_intent_id == trim.id
            )
        ).one()
    assert dependent_after.id == dependent_before.id
    assert dependent_after.state == "queued"
    assert dependent_after.provider_event_id == dependent_before.provider_event_id


def test_occurrence_master_drift_converges_without_any_owner_action(tmp_path):
    """C: the exact loop real owner acceptance hit.

    A `This event` write embeds the master's ETag in its recurrence identity.
    When Google's master moved, resolution rejected the write as an identity
    failure -- and because that never consumed an attempt, every retry and every
    `Apply my Ion changes` re-derived the same stale identity and failed the
    same way, producing "Google changed this event again" indefinitely.

    The master handed to resolution is freshly fetched provider state, so its
    ETag is adopted and the write proceeds.
    """
    engine, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    original = ProviderDateTime(
        date_time="2030-01-08T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    intent = _edit(
        writes,
        master,
        recurrence_scope="occurrence",
        occurrence_original_start=original,
        title="Renamed one occurrence",
    )
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )

    resolved = writes.resolve_occurrence(
        intent.id,
        ResolveProviderOccurrenceInput(
            master=_recurring_provider_event(
                etag='"master-moved-in-google"', recurrence=["RRULE:FREQ=WEEKLY"]
            ),
            instance=_recurring_provider_event(
                provider_event_id="synthetic-instance",
                etag='"instance-etag"',
                recurring_event_id="synthetic-provider-event",
                original_start=original,
            ),
        ),
    )
    assert resolved.state == "attempting", "master drift must not stop the write"
    assert (
        resolved.base_values.recurrence_identity.master_provider_etag
        == '"master-moved-in-google"'
    )
    # The confirmed link is aligned too, so the next preflight and any sibling
    # occurrence agree with what the provider just reported.
    with engine.connect() as connection:
        assert (
            connection.execute(
                select(google_event_links.c.provider_etag).where(
                    google_event_links.c.calendar_block_id == master.id
                )
            ).scalar_one()
            == '"master-moved-in-google"'
        )

    projected = next(item for item in calendar.status().blocks if item.id == master.id)
    assert projected.provider_write_state == "pending"

    completed = writes.reconcile_patch(
        intent.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=_recurring_provider_event(
                provider_event_id="synthetic-instance",
                etag='"instance-etag-2"',
                title="Renamed one occurrence",
                recurring_event_id="synthetic-provider-event",
                original_start=original,
            ),
        ),
    )
    assert completed.state == "completed"
    assert all(
        block.provider_write_state != "conflict" for block in calendar.status().blocks
    )


def test_legacy_conflict_rows_are_requeued_under_the_new_policy(tmp_path):
    """F: a row conflicted by the superseded policy must not trap the owner in
    a workflow the product no longer has. It is re-armed against confirmed
    authority; its original conflict audit stays on the record."""
    engine, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block)
    with engine.begin() as connection:
        connection.execute(
            update(calendar_provider_write_intents)
            .where(calendar_provider_write_intents.c.id == intent.id)
            .values(
                state="conflict",
                failure_class="stale_precondition",
                failure_reason="provider_etag_changed_during_refresh",
                attempt_count=1,
            )
        )
        connection.execute(
            update(google_event_links)
            .where(google_event_links.c.calendar_block_id == block.id)
            .values(provider_etag='"google-latest"')
        )
    stuck = next(item for item in calendar.status().blocks if item.id == block.id)
    assert stuck.provider_write_state == "conflict"

    result = writes.recover(RecoverWriteIntentsInput())
    assert result.legacy_conflicts_requeued == 1

    settled = next(item for item in calendar.status().blocks if item.id == block.id)
    assert settled.provider_write_state == "pending"
    plan = writes.ready(ReadyWriteIntentsInput())[0]
    assert plan.id == intent.id
    assert plan.expected_provider_etag == '"google-latest"'
    assert plan.desired_values.title == "Synthetic revised title", (
        "the owner's original intent must survive the reclassification"
    )
    # History is preserved: the original conflict remains in the audit trail.
    with engine.connect() as connection:
        actions = (
            connection.execute(
                select(calendar_provider_write_audit.c.action).where(
                    calendar_provider_write_audit.c.intent_id == intent.id
                )
            )
            .scalars()
            .all()
        )
    assert "write_intent_ready" in actions


def test_a_genuinely_unmergeable_conflict_is_not_requeued(tmp_path):
    """G: recovery must not launder a real contradiction into a retry."""
    engine, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block)
    with engine.begin() as connection:
        connection.execute(
            update(calendar_provider_write_intents)
            .where(calendar_provider_write_intents.c.id == intent.id)
            .values(
                state="conflict",
                failure_class="provider_not_found",
                failure_reason="provider_event_absent_during_refresh",
                attempt_count=1,
            )
        )
    result = writes.recover(RecoverWriteIntentsInput())
    assert result.legacy_conflicts_requeued == 0
    still = next(item for item in calendar.status().blocks if item.id == block.id)
    assert still.provider_write_state == "conflict"
    assert still.provider_write_failure_class == "provider_not_found"


def test_unsettled_provider_work_never_removes_the_owners_affordances(tmp_path):
    """The literal form of "you cannot edit yet": eligibility used to require a
    settled provider state, so an in-flight write removed the Edit button and
    the drag handles. Eligibility describes whether Ion can accept a direct
    human write, not whether the provider happens to be idle."""
    _, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block, title="First value")
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.provider_write_state == "pending"
    assert projected.provider_write_capability.eligible is True
    assert projected.provider_write_capability.reason == "eligible"
    assert projected.provider_delete_capability.eligible is True


def test_a_pending_create_still_guards_deletion(tmp_path):
    """The one exception: deleting before Ion knows whether Google made the
    event could orphan it, so that case stays explicit."""
    _, calendar, writes, _block = _connected(tmp_path)
    created = _create(writes, calendar)
    writes.begin_attempt(
        created.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    pending = next(
        item
        for item in calendar.status().blocks
        if item.provider_write_operation == "create"
    )
    assert pending.provider_delete_capability.eligible is False
    assert pending.provider_delete_capability.reason == "create_reconciliation_required"


def test_rapid_successive_edits_supersede_obsolete_unattempted_writes(tmp_path):
    """1 & 2 & 3: the owner drags the same event three times without waiting.

    Nothing is in flight between the gestures, so the obsolete positions are
    retired instead of each costing a provider round-trip, and the final human
    value is the one that dispatches.
    """
    _, calendar, writes, block = _connected(tmp_path)
    first = _edit(writes, block, title="Dragged to 3 PM")
    second = _edit(writes, block, title="Dragged to 4 PM")
    third = _edit(writes, block, title="Dragged to 5 PM")

    assert third.state == "ready", "the newest human intent is what dispatches"
    plans = writes.ready(ReadyWriteIntentsInput())
    assert [plan.id for plan in plans] == [third.id], (
        "obsolete intermediate positions must not each cost a provider write"
    )
    assert plans[0].desired_values.title == "Dragged to 5 PM"

    with writes.engine.connect() as connection:
        states = dict(
            connection.execute(
                select(
                    calendar_provider_write_intents.c.id,
                    calendar_provider_write_intents.c.state,
                )
            ).all()
        )
    assert states[first.id] == "cancelled"
    assert states[second.id] == "cancelled"

    # The Calendar shows the newest human intent, never an obsolete one.
    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.provider_write_overlay.title == "Dragged to 5 PM"
    assert projected.provider_write_state == "pending"


def test_an_edit_during_an_in_flight_write_waits_without_blocking_the_owner(tmp_path):
    """4: the first request is genuinely attempting when the owner acts again.

    The newer intent is accepted immediately and durably, no parallel write is
    dispatched to the same target, and it is released and re-aimed at the
    authority the first attempt confirmed.
    """
    _, calendar, writes, block = _connected(tmp_path)
    first = _edit(writes, block, title="First value")
    writes.begin_attempt(
        first.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )

    second = _edit(writes, block, title="Second value")
    assert second.state == "queued", "accepted durably, not refused"
    assert writes.ready(ReadyWriteIntentsInput()) == [], (
        "no parallel provider write may target the same event"
    )
    # The owner already sees their newest value while the first still settles.
    mid_flight = next(item for item in calendar.status().blocks if item.id == block.id)
    assert mid_flight.provider_write_overlay.title == "Second value"

    completed = writes.reconcile_patch(
        first.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=_google_event(provider_etag='"after-first"', title="First value"),
        ),
    )
    assert completed.state == "completed"

    # Released automatically, and re-aimed at the ETag the first write left.
    released = writes.ready(ReadyWriteIntentsInput())
    assert [plan.id for plan in released] == [second.id]
    writes.begin_attempt(
        second.id,
        BeginWriteAttemptInput(expected_state="ready", executor_provenance="recovery"),
    )
    with writes.engine.connect() as connection:
        rearmed = connection.execute(
            select(calendar_provider_write_intents.c.expected_provider_etag).where(
                calendar_provider_write_intents.c.id == second.id
            )
        ).scalar_one()
    assert rearmed == '"after-first"'

    settled = writes.reconcile_patch(
        second.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=_google_event(provider_etag='"after-second"', title="Second value"),
        ),
    )
    assert settled.state == "completed"
    final = next(item for item in calendar.status().blocks if item.id == block.id)
    assert final.title == "Second value"
    assert final.provider_write_state == "synced"


def test_the_projection_never_snaps_back_to_a_superseded_value(tmp_path):
    """The confirmed value moving to an obsolete intermediate state must not be
    what the owner sees. Ion keeps showing the newest human intent."""
    _, calendar, writes, block = _connected(tmp_path)
    first = _edit(writes, block, title="Intermediate")
    writes.begin_attempt(
        first.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    _edit(writes, block, title="Newest")

    writes.reconcile_patch(
        first.id,
        ReconcileProviderPatchInput(
            resolution_kind="patch_response",
            event=_google_event(provider_etag='"v2"', title="Intermediate"),
        ),
    )
    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.title == "Newest", "no flicker through the superseded value"
    assert projected.provider_write_state != "conflict"


def test_read_sync_between_successive_human_edits_creates_no_review(tmp_path):
    """5: a Google refresh lands mid-sequence. Untouched provider fields merge;
    the newest human field keeps projecting; nothing becomes a review task."""
    _, calendar, writes, block = _connected(tmp_path)
    first = _edit(writes, block, title="First value")
    writes.begin_attempt(
        first.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    _edit(writes, block, title="Second value")

    calendar_id = calendar.status().calendars[0].id
    generation = str(uuid4())
    calendar.begin_sync(calendar_id, SyncBeginInput(generation=generation, mode="full"))
    calendar.apply_sync_page(
        calendar_id,
        SyncPageInput(
            generation=generation,
            events=[_google_event(provider_etag='"mid"', location="Room Q")],
        ),
    )
    calendar.complete_sync(
        calendar_id,
        SyncCompleteInput(generation=generation, next_sync_token="synthetic-sync-2"),
    )

    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.location == "Room Q"
    assert projected.provider_write_overlay.title == "Second value"
    assert projected.provider_write_state == "pending"


def test_repeated_this_event_edits_keep_one_immutable_occurrence_identity(tmp_path):
    """6: the same occurrence edited twice before settlement."""
    _, calendar, writes, master = _connected(
        tmp_path, event_overrides={"recurrence": ["RRULE:FREQ=WEEKLY"]}
    )
    original = ProviderDateTime(
        date_time="2030-01-08T09:00:00-08:00",
        timezone="America/Los_Angeles",
    )
    first = _edit(
        writes,
        master,
        recurrence_scope="occurrence",
        occurrence_original_start=original,
        title="Occurrence first",
    )
    second = _edit(
        writes,
        master,
        recurrence_scope="occurrence",
        occurrence_original_start=original,
        title="Occurrence second",
    )
    assert second.state == "ready"
    plans = writes.ready(ReadyWriteIntentsInput())
    assert [plan.id for plan in plans] == [second.id]
    assert plans[0].desired_values.title == "Occurrence second"
    # The occurrence's immutable identity survives supersession intact.
    assert (
        plans[0].base_values.recurrence_identity.original_start.date_time
        == original.date_time
    )
    with writes.engine.connect() as connection:
        assert (
            connection.execute(
                select(calendar_provider_write_intents.c.state).where(
                    calendar_provider_write_intents.c.id == first.id
                )
            ).scalar_one()
            == "cancelled"
        )


def test_no_ordinary_human_mutation_lifecycle_produces_a_recovery_condition(tmp_path):
    """The structural guarantee behind the rewrite.

    Walk an ordinary direct-human edit through every stage of its lifecycle --
    queue, attempt, provider drift, re-read, rebase, retry, confirm -- and
    assert the renderer is never handed a condition to decide. `provider_
    recovery_kind` is the only channel by which the Calendar can ask the owner
    to settle something, and an ordinary mutation must never populate it.
    """
    _, calendar, writes, block = _connected(tmp_path)

    def recovery_kinds():
        return [item.provider_recovery_kind for item in calendar.status().blocks]

    intent = _edit(writes, block, title="Ordinary change")
    assert recovery_kinds() == [None]

    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    assert recovery_kinds() == [None]

    # Google moved underneath the write.
    drifted = writes.record_result(
        intent.id,
        RecordProviderWriteResultInput(
            stage="patch",
            result_class="stale_precondition",
            safe_reason="provider_values_changed",
        ),
    )
    assert drifted.state == "ambiguous"
    assert recovery_kinds() == [None], "ordinary drift is not the owner's problem"

    # Ion re-reads confirmed state and rebases.
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ambiguous", executor_provenance="recovery"
        ),
    )
    rebased = writes.reconcile_patch(
        intent.id,
        ReconcileProviderPatchInput(
            resolution_kind="identity_lookup",
            event=_google_event(provider_etag='"moved"', location="Room R"),
        ),
    )
    assert rebased.state == "ready"
    assert recovery_kinds() == [None]

    # A background refresh lands mid-flight.
    calendar_id = calendar.status().calendars[0].id
    generation = str(uuid4())
    calendar.begin_sync(calendar_id, SyncBeginInput(generation=generation, mode="full"))
    calendar.apply_sync_page(
        calendar_id,
        SyncPageInput(
            generation=generation,
            events=[_google_event(provider_etag='"moved-again"', location="Room S")],
        ),
    )
    calendar.complete_sync(
        calendar_id,
        SyncCompleteInput(generation=generation, next_sync_token="synthetic-sync-2"),
    )
    assert recovery_kinds() == [None]

    # The owner acts again while the first is still unsettled, against the
    # revision the renderer currently holds.
    current = next(item for item in calendar.status().blocks if item.id == block.id)
    _edit(
        writes,
        block,
        expected_block_revision=current.revision,
        title="Second ordinary change",
    )
    assert recovery_kinds() == [None]

    # And recovery, which used to manufacture review tasks, produces none.
    writes.recover(RecoverWriteIntentsInput())
    assert recovery_kinds() == [None]


def test_a_genuine_exception_names_itself_specifically(tmp_path):
    """The other half: real contradictions still reach the owner, each as its
    own named condition rather than a generic decision."""
    _, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block)
    writes.begin_attempt(
        intent.id,
        BeginWriteAttemptInput(
            expected_state="ready", executor_provenance="direct_human"
        ),
    )
    writes.record_result(
        intent.id,
        RecordProviderWriteResultInput(
            stage="patch",
            result_class="provider_not_found",
            safe_reason="provider_deleted",
        ),
    )
    projected = next(item for item in calendar.status().blocks if item.id == block.id)
    assert projected.provider_recovery_kind == "provider_deleted"
