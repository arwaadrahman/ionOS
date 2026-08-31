import json
import re
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import select, update
from test_migrations import migration_config

from ion_api.calendar import CalendarService, CalendarValidationError
from ion_api.calendar_contracts import (
    CALENDAR_LIST_SCOPE,
    EVENTS_READ_SCOPE,
    EVENTS_WRITE_SCOPE,
    GoogleAccountConnectInput,
    ProviderCalendarInput,
    ProviderDateTime,
    ProviderEventInput,
    SyncBeginInput,
    SyncCompleteInput,
    SyncPageInput,
)
from ion_api.calendar_write_contracts import (
    BeginWriteAttemptInput,
    CreateProviderEventInput,
    DeleteProviderEventInput,
    EditProviderEventInput,
    ProviderWriteValues,
    PruneWriteIntentsInput,
    QueueProviderWriteIntentInput,
    ReadyWriteIntentsInput,
    ReconcileProviderCreateInput,
    ReconcileProviderDeleteInput,
    ReconcileProviderPatchInput,
    RecordProviderWriteResultInput,
    RecoverWriteIntentsInput,
    WriteIntentTransitionInput,
)
from ion_api.calendar_writes import (
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
        ({"recurrence": ["RRULE:FREQ=DAILY"]}, "recurrence_unsupported"),
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


def test_ion_locked_event_requires_explicit_confirmation(tmp_path):
    engine, _, writes, block = _connected(tmp_path)
    with engine.begin() as connection:
        connection.execute(
            update(calendar_block_ion_metadata)
            .where(calendar_block_ion_metadata.c.calendar_block_id == block.id)
            .values(flexibility="locked")
        )
    with pytest.raises(CalendarValidationError, match="locked_confirmation_required"):
        _edit(writes, block, locked_confirmed=False)
    assert _edit(writes, block, locked_confirmed=True).state == "ready"


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
    after_due = restarted.recover(RecoverWriteIntentsInput(now="2030-01-01T12:05:00Z"))
    assert after_due.retry_wait_to_ready == 1
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


def test_local_first_title_edit_overlays_confirmed_base_and_reconciles_patch(tmp_path):
    engine, calendar, writes, block = _connected(tmp_path)
    intent = _edit(writes, block)
    assert intent.state == "ready"
    projected = calendar.status().blocks[0]
    assert projected.title == "Synthetic revised title"
    assert projected.provider_write_state == "pending"
    assert projected.provider_write_detail == "ready"
    assert projected.provider_write_capability.reason == "write_pending"

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
    with pytest.raises(CalendarValidationError, match="preserve"):
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
        ("stale_precondition", "conflict"),
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


def test_provider_refresh_preserves_pending_overlay_and_detects_etag_drift(tmp_path):
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
    assert status.title == "Synthetic provider-side title"
    assert status.provider_write_state == "conflict"
    with engine.connect() as connection:
        stored = connection.execute(
            select(calendar_provider_write_intents).where(
                calendar_provider_write_intents.c.id == intent.id
            )
        ).one()
    assert json.loads(stored.desired_values_json)["title"] == "Synthetic revised title"
    assert stored.state == "conflict"


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        ("calendar_read_only", "access_role_read_only"),
        ("calendar_deleted", "calendar_deleted"),
        ("account_read_only", "account_read_only"),
    ],
)
def test_patch_dispatch_rechecks_capability_loss(tmp_path, mutation, reason):
    engine, _, writes, block = _connected(tmp_path)
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
