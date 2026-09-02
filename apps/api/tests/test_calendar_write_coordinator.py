"""Phase 2C-R0 domain tests for the direct-human write coordinator.

These assert the architectural claim R0 exists to make: human intent acceptance
and provider write execution are separate concerns, and no path through the
coordinator can produce a generic review decision.
"""

import json

import pytest
from calendar_write_fixtures import BLOCK_ID, seed_writable_event
from sqlalchemy import select

from ion_api.calendar_write_contracts import DirectHumanIntentInput
from ion_api.calendar_write_coordinator import (
    CalendarWriteCoordinator,
    CalendarWriteIneligible,
    CalendarWriteRevisionConflict,
)
from ion_api.calendar_write_model import (
    AUTOMATIC_RECOVERY,
    COORDINATOR_UNUSED_AUDIT_ACTIONS,
    COORDINATOR_UNUSED_STATES,
    FORBIDDEN_RECOVERY,
    OWNER_ACTION_RECOVERY,
    WriteFailureClass,
    load_vocabulary,
)
from ion_api.db import create_database_engine
from ion_api.migrations import upgrade_to_head
from ion_api.schema import (
    calendar_provider_write_audit,
    calendar_provider_write_intents,
)


def coordinator(tmp_path, **seed):
    tmp_path.mkdir(parents=True, exist_ok=True)
    database = tmp_path / "ion.sqlite3"
    upgrade_to_head(database)
    engine = create_database_engine(database)
    seed_writable_event(engine, **seed)
    return CalendarWriteCoordinator(engine), engine


def intent(command="11111111-1111-4111-8111-111111111111", title="Renamed"):
    return DirectHumanIntentInput(
        command_id=command,
        operation="patch",
        expected_revision=1,
        changed_fields=["title"],
        draft={"title": title},
    )


def test_a_direct_human_action_is_accepted_durably_and_authorizes_itself(tmp_path):
    write, engine = coordinator(tmp_path)
    receipt = write.accept_direct_human_intent(BLOCK_ID, intent())

    assert receipt.accepted is True
    assert receipt.state == "ready"
    assert receipt.awaiting_predecessor is False

    with engine.begin() as connection:
        row = connection.execute(select(calendar_provider_write_intents)).one()
    # Durable before any provider work, and no attempt has been made.
    assert row.provenance == "direct_human"
    assert row.attempt_count == 0
    assert row.last_attempt_at is None
    # Provider authority was derived server-side, never supplied by the caller.
    assert row.expected_provider_etag == '"synthetic-etag-1"'
    assert row.provider_event_id.startswith("synthetic-event-")


def test_provider_serialization_never_becomes_a_human_edit_lock(tmp_path):
    """The Phase 2C v1 defect this architecture exists to prevent.

    There, a second edit while a write was outstanding was refused with
    `write_pending`. Here the newer human intent is accepted durably regardless,
    and only the *provider* lane serializes.
    """

    write, _ = coordinator(tmp_path)
    first = write.accept_direct_human_intent(BLOCK_ID, intent())
    write.begin_attempt(first.intent_id)

    # An edit arriving while provider work is genuinely in flight.
    second = write.accept_direct_human_intent(
        BLOCK_ID, intent(command="22222222-2222-4222-8222-222222222222")
    )
    assert second.accepted is True
    assert second.awaiting_predecessor is True
    assert second.sequence == first.sequence + 1
    # And a third, immediately after, still accepted.
    third = write.accept_direct_human_intent(
        BLOCK_ID, intent(command="33333333-3333-4333-8333-333333333333")
    )
    assert third.accepted is True

    # The provider lane still gets exactly one write per target, and never
    # races or cancels the in-flight one.
    work = write.select_provider_work()
    assert work.plans == []
    assert work.provider_busy is True


def test_a_waiting_intent_is_released_when_its_predecessor_settles(tmp_path):
    write, _ = coordinator(tmp_path)
    first = write.accept_direct_human_intent(BLOCK_ID, intent())
    write.begin_attempt(first.intent_id)
    second = write.accept_direct_human_intent(
        BLOCK_ID, intent(command="22222222-2222-4222-8222-222222222222")
    )

    assert write.record_outcome(first.intent_id, "success") is None
    work = write.select_provider_work()
    assert [plan.intent_id for plan in work.plans] == [second.intent_id]
    assert work.provider_busy is False


def test_ordinary_provider_drift_is_automatic_and_never_reaches_the_owner(tmp_path):
    write, engine = coordinator(tmp_path)
    receipt = write.accept_direct_human_intent(BLOCK_ID, intent())
    write.begin_attempt(receipt.intent_id)

    recovery = write.record_outcome(receipt.intent_id, "stale_precondition")
    assert recovery == "provider_version_drift"
    assert recovery in AUTOMATIC_RECOVERY
    assert recovery not in OWNER_ACTION_RECOVERY

    result = write.recover()
    entry = next(item for item in result.entries if item.intent_id == receipt.intent_id)
    assert entry.automatic is True
    assert entry.owner_action is False
    # Re-armed for another bounded attempt rather than escalated.
    assert entry.state == "ready"

    with engine.begin() as connection:
        states = {
            row.state
            for row in connection.execute(select(calendar_provider_write_intents))
        }
    assert states.isdisjoint(COORDINATOR_UNUSED_STATES)


def test_drift_that_outlasts_the_budget_is_named_not_turned_into_a_conflict(tmp_path):
    write, _ = coordinator(tmp_path)
    receipt = write.accept_direct_human_intent(BLOCK_ID, intent())
    recovery = None
    for _ in range(5):
        write.begin_attempt(receipt.intent_id)
        recovery = write.record_outcome(receipt.intent_id, "stale_precondition")
        write.recover()
    # Exhaustion is not a disagreement about facts, so it does not borrow the
    # language of one. It names what actually happened.
    assert recovery == "automatic_recovery_exhausted"
    assert recovery in OWNER_ACTION_RECOVERY
    assert recovery not in FORBIDDEN_RECOVERY


def test_the_coordinator_can_never_produce_a_generic_review_state(tmp_path):
    """Every failure class, driven end to end, and none yields a generic state."""

    from typing import get_args

    produced_states: set[str] = set()
    produced_recovery: set[str | None] = set()
    for index, failure in enumerate(get_args(WriteFailureClass)):
        write, engine = coordinator(tmp_path / f"case{index}")
        receipt = write.accept_direct_human_intent(BLOCK_ID, intent())
        write.begin_attempt(receipt.intent_id)
        produced_recovery.add(write.record_outcome(receipt.intent_id, failure))
        with engine.begin() as connection:
            produced_states.update(
                row.state
                for row in connection.execute(select(calendar_provider_write_intents))
            )
            produced_actions = {
                row.action
                for row in connection.execute(select(calendar_provider_write_audit))
            }
        assert produced_actions.isdisjoint(COORDINATOR_UNUSED_AUDIT_ACTIONS)

    assert produced_states.isdisjoint(COORDINATOR_UNUSED_STATES)
    assert produced_recovery.isdisjoint(FORBIDDEN_RECOVERY)
    # Classification is total: every failure class mapped to something named.
    assert None in produced_recovery  # success
    assert produced_recovery - {None} <= AUTOMATIC_RECOVERY | OWNER_ACTION_RECOVERY


def test_a_restart_repairs_an_in_flight_attempt_to_ambiguous(tmp_path):
    write, _ = coordinator(tmp_path)
    receipt = write.accept_direct_human_intent(BLOCK_ID, intent())
    write.begin_attempt(receipt.intent_id)

    # Simulates the process dying mid-request: the row says `attempting`, but
    # the true provider outcome is unknown and must not be silently retried.
    result = write.recover()
    assert result.repaired_in_flight == 1
    entry = next(item for item in result.entries if item.intent_id == receipt.intent_id)
    assert entry.state == "ambiguous"
    assert write.select_provider_work().plans == []


def test_r0_dispatches_nothing(tmp_path):
    write, _ = coordinator(tmp_path)
    write.accept_direct_human_intent(BLOCK_ID, intent())
    plans = write.select_provider_work().plans
    assert len(plans) == 1
    # The plan exists and is serialized correctly; nothing may leave for Google
    # until R1 adds a dispatch path behind its own real-Google acceptance gate.
    assert plans[0].dispatchable is False


@pytest.mark.parametrize(
    "seed",
    [
        {"write_granted": False},
        {"access_role": "reader"},
        {"has_attendees": True},
        {"provider_locked": True},
        {"provider_event_type": "special"},
        {"link_state": "pending_create"},
    ],
)
def test_ineligible_provider_targets_are_refused_on_validity_grounds(tmp_path, seed):
    write, _ = coordinator(tmp_path, **seed)
    with pytest.raises(CalendarWriteIneligible):
        write.accept_direct_human_intent(BLOCK_ID, intent())


def test_a_stale_canonical_revision_is_an_ion_local_check_not_a_provider_conflict(
    tmp_path,
):
    write, _ = coordinator(tmp_path)
    stale = DirectHumanIntentInput(
        command_id="11111111-1111-4111-8111-111111111111",
        operation="patch",
        expected_revision=9,
        changed_fields=["title"],
        draft={"title": "Renamed"},
    )
    with pytest.raises(CalendarWriteRevisionConflict):
        write.accept_direct_human_intent(BLOCK_ID, stale)


def test_changed_fields_must_describe_exactly_the_draft(tmp_path):
    with pytest.raises(ValueError):
        DirectHumanIntentInput(
            command_id="11111111-1111-4111-8111-111111111111",
            operation="patch",
            expected_revision=1,
            changed_fields=["start"],
            draft={"title": "Renamed"},
        )
    with pytest.raises(ValueError):
        DirectHumanIntentInput(
            command_id="11111111-1111-4111-8111-111111111111",
            operation="patch",
            expected_revision=1,
            changed_fields=["title", "title"],
            draft={"title": "Renamed"},
        )


def test_a_temporal_value_is_all_day_or_zoned_never_both(tmp_path):
    ok = DirectHumanIntentInput(
        command_id="11111111-1111-4111-8111-111111111111",
        operation="patch",
        expected_revision=1,
        changed_fields=["start"],
        draft={"start": {"date_time": "2030-01-07T19:00:00Z", "time_zone": "UTC"}},
    )
    assert ok.draft.start is not None
    with pytest.raises(ValueError):
        DirectHumanIntentInput(
            command_id="11111111-1111-4111-8111-111111111111",
            operation="patch",
            expected_revision=1,
            changed_fields=["start"],
            draft={"start": {"date": "2030-01-07", "time_zone": "UTC"}},
        )


def test_python_vocabularies_match_the_canonical_cross_layer_manifest():
    """Python, Rust, and TypeScript all assert against this same file."""

    from typing import get_args

    from ion_api.calendar_write_model import (
        ACCEPTED_OPERATIONS,
        ACCEPTED_RECURRENCE_SCOPES,
        CHANGED_FIELDS,
        DISPATCHABLE_OPERATIONS,
        WriteAuditAction,
        WriteIntentState,
        WriteOperation,
        WriteRecurrenceScope,
    )

    manifest = load_vocabulary()
    assert list(get_args(WriteOperation)) == manifest["storage"]["operations"]
    assert (
        list(get_args(WriteRecurrenceScope)) == manifest["storage"]["recurrence_scopes"]
    )
    assert list(get_args(WriteIntentState)) == manifest["storage"]["intent_states"]
    assert list(get_args(WriteFailureClass)) == manifest["storage"]["failure_classes"]
    assert list(get_args(WriteAuditAction)) == manifest["storage"]["audit_actions"]
    assert sorted(ACCEPTED_OPERATIONS) == sorted(
        manifest["coordinator"]["accepted_operations"]
    )
    assert sorted(ACCEPTED_RECURRENCE_SCOPES) == sorted(
        manifest["coordinator"]["accepted_recurrence_scopes"]
    )
    assert sorted(CHANGED_FIELDS) == sorted(manifest["coordinator"]["changed_fields"])
    assert sorted(DISPATCHABLE_OPERATIONS) == sorted(
        manifest["coordinator"]["dispatchable_operations"]
    )
    assert sorted(AUTOMATIC_RECOVERY) == sorted(manifest["recovery"]["automatic"])
    assert sorted(OWNER_ACTION_RECOVERY) == sorted(manifest["recovery"]["owner_action"])
    assert sorted(FORBIDDEN_RECOVERY) == sorted(manifest["recovery"]["forbidden"])


def test_the_storage_vocabulary_matches_immutable_migration_0007(tmp_path):
    """Storage vocabulary is fixed by 0007 and may not drift from the model."""

    database = tmp_path / "ion.sqlite3"
    upgrade_to_head(database)
    engine = create_database_engine(database)
    with engine.begin() as connection:
        sql = connection.exec_driver_sql(
            "SELECT sql FROM sqlite_master WHERE name = "
            "'calendar_provider_write_intents'"
        ).scalar()
    manifest = load_vocabulary()
    for state in manifest["storage"]["intent_states"]:
        assert f"'{state}'" in sql
    for failure in manifest["storage"]["failure_classes"]:
        assert f"'{failure}'" in sql
    assert "provenance = 'direct_human'" in sql


def test_audit_records_only_safe_evidence(tmp_path):
    write, engine = coordinator(tmp_path)
    receipt = write.accept_direct_human_intent(BLOCK_ID, intent(title="Secret title"))
    write.begin_attempt(receipt.intent_id)
    write.record_outcome(receipt.intent_id, "terminal_provider_rejection", "rejected")

    with engine.begin() as connection:
        rows = connection.execute(select(calendar_provider_write_audit)).all()
    assert rows
    for row in rows:
        serialized = json.dumps(dict(row._mapping))
        # Never event content, account identity, or a raw provider resource.
        assert "Secret title" not in serialized
        assert "example.invalid" not in serialized
        assert "synthetic-etag" not in serialized
