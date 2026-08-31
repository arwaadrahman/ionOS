import json
import re
from uuid import uuid4

import pytest
from alembic import command
from fastapi.testclient import TestClient
from sqlalchemy import select
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
    ProviderWriteValues,
    PruneWriteIntentsInput,
    QueueProviderWriteIntentInput,
    ReadyWriteIntentsInput,
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
    calendar_provider_write_audit,
    calendar_provider_write_intents,
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
    with pytest.raises(CalendarValidationError, match=reason):
        _queue(writes, block)


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
            "eligible": True,
            "reason": "eligible",
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
