"""Phase 2C-R1 domain tests: ordinary event edit.

R1's whole claim is that one ordinary event can be edited twice in succession
and both edits settle automatically. These tests drive that, plus the automatic
ETag rebase that makes ordinary provider drift an internal event rather than a
decision handed to the owner.
"""

import json

from calendar_write_fixtures import BLOCK_ID, seed_writable_event
from sqlalchemy import select

from ion_api.calendar_write_contracts import (
    ConfirmedProviderEvent,
    DirectHumanIntentInput,
)
from ion_api.calendar_write_coordinator import (
    CalendarWriteCoordinator,
    pending_changed_fields,
    pending_human_overlay,
)
from ion_api.db import create_database_engine
from ion_api.migrations import upgrade_to_head
from ion_api.schema import calendar_blocks, calendar_provider_write_intents


def coordinator(tmp_path, **seed):
    tmp_path.mkdir(parents=True, exist_ok=True)
    database = tmp_path / "ion.sqlite3"
    upgrade_to_head(database)
    engine = create_database_engine(database)
    seed_writable_event(engine, **seed)
    return CalendarWriteCoordinator(engine), engine


def edit(title, command):
    return DirectHumanIntentInput(
        command_id=command,
        operation="patch",
        expected_revision=1,
        changed_fields=["title"],
        draft={"title": title},
    )


def confirmed(etag, title=None, **kwargs):
    return ConfirmedProviderEvent(provider_etag=etag, title=title, **kwargs)


def overlay_for(engine, block_id=BLOCK_ID):
    with engine.connect() as connection:
        overlay, recovery = pending_human_overlay(connection)
    return overlay.get(block_id, {}), recovery


def block_title(engine, block_id=BLOCK_ID):
    with engine.connect() as connection:
        return connection.execute(
            select(calendar_blocks.c.title).where(calendar_blocks.c.id == block_id)
        ).scalar()


# --- 1. Ordinary edit -------------------------------------------------------


def test_an_ordinary_edit_is_visible_immediately_and_settles_automatically(tmp_path):
    write, engine = coordinator(tmp_path)
    receipt = write.accept_direct_human_intent(
        BLOCK_ID, edit("B", "11111111-1111-4111-8111-111111111111")
    )
    # Optimistic: the owner sees B before Google has heard about it.
    assert overlay_for(engine)[0] == {"title": "B"}
    assert block_title(engine) == "Synthetic study block"

    plans = write.select_provider_work().plans
    assert len(plans) == 1 and plans[0].dispatchable
    assert plans[0].expected_provider_etag == '"synthetic-etag-1"'
    write.begin_attempt(receipt.intent_id)
    result = write.record_outcome(
        receipt.intent_id, "success", confirmed=confirmed('"etag-2"', title="B")
    )
    assert result.recovery is None and result.state == "completed"

    # Settled: the overlay collapses onto confirmed canonical state.
    assert overlay_for(engine) == ({}, [])
    assert block_title(engine) == "B"


# --- 2. Second edit after the first confirms --------------------------------


def test_a_second_edit_after_confirmation_settles_automatically(tmp_path):
    write, engine = coordinator(tmp_path)
    first = write.accept_direct_human_intent(
        BLOCK_ID, edit("B", "11111111-1111-4111-8111-111111111111")
    )
    write.begin_attempt(first.intent_id)
    write.record_outcome(first.intent_id, "success", confirmed=confirmed('"e2"', "B"))

    second = write.accept_direct_human_intent(
        BLOCK_ID, edit("C", "22222222-2222-4222-8222-222222222222")
    )
    assert second.accepted and second.state == "ready"
    assert overlay_for(engine)[0] == {"title": "C"}
    write.begin_attempt(second.intent_id)
    write.record_outcome(second.intent_id, "success", confirmed=confirmed('"e3"', "C"))
    assert block_title(engine) == "C"
    assert overlay_for(engine) == ({}, [])


# --- 3. Second edit BEFORE the first confirms -- R1's main case -------------


def test_a_second_edit_while_the_first_is_in_flight(tmp_path):
    write, engine = coordinator(tmp_path)
    first = write.accept_direct_human_intent(
        BLOCK_ID, edit("B", "11111111-1111-4111-8111-111111111111")
    )
    write.begin_attempt(first.intent_id)  # genuinely in flight

    second = write.accept_direct_human_intent(
        BLOCK_ID, edit("C", "22222222-2222-4222-8222-222222222222")
    )
    assert second.accepted is True
    assert second.superseded_intent_id is None  # never cancels an in-flight write
    # C is what the owner sees, immediately and throughout.
    assert overlay_for(engine)[0] == {"title": "C"}
    # No parallel provider write against the same target.
    work = write.select_provider_work()
    assert work.plans == [] and work.provider_busy is True

    # The first settles internally. It must not become visibly authoritative.
    write.record_outcome(first.intent_id, "success", confirmed=confirmed('"e2"', "B"))
    assert overlay_for(engine)[0] == {"title": "C"}
    assert block_title(engine) == "Synthetic study block"  # B never displaced C

    # The successor is released and re-aimed at the ETag that attempt confirmed.
    plans = write.select_provider_work().plans
    assert [plan.intent_id for plan in plans] == [second.intent_id]
    assert plans[0].expected_provider_etag == '"e2"'

    write.begin_attempt(second.intent_id)
    write.record_outcome(second.intent_id, "success", confirmed=confirmed('"e3"', "C"))
    assert block_title(engine) == "C"
    assert overlay_for(engine) == ({}, [])


# --- 4. Three rapid edits ---------------------------------------------------


def test_three_rapid_edits_coalesce_and_the_newest_wins(tmp_path):
    write, engine = coordinator(tmp_path)
    b = write.accept_direct_human_intent(
        BLOCK_ID, edit("B", "11111111-1111-4111-8111-111111111111")
    )
    c = write.accept_direct_human_intent(
        BLOCK_ID, edit("C", "22222222-2222-4222-8222-222222222222")
    )
    d = write.accept_direct_human_intent(
        BLOCK_ID, edit("D", "33333333-3333-4333-8333-333333333333")
    )
    # Nothing had left, so the obsolete values cost no provider round-trip.
    assert c.superseded_intent_id == b.intent_id
    assert d.superseded_intent_id == c.intent_id
    assert overlay_for(engine)[0] == {"title": "D"}

    plans = write.select_provider_work().plans
    assert [plan.intent_id for plan in plans] == [d.intent_id]
    write.begin_attempt(d.intent_id)
    write.record_outcome(d.intent_id, "success", confirmed=confirmed('"e2"', "D"))
    assert block_title(engine) == "D"


# --- 5. Provider revision drift on an untouched field -----------------------


def test_drift_on_an_untouched_field_lets_both_changes_survive(tmp_path):
    write, engine = coordinator(tmp_path)
    receipt = write.accept_direct_human_intent(
        BLOCK_ID, edit("B", "11111111-1111-4111-8111-111111111111")
    )
    write.begin_attempt(receipt.intent_id)
    # Google independently moved the time; Ion changed only the title.
    google = confirmed(
        '"etag-moved"',
        title="Synthetic study block",
        start={"date_time": "2030-01-07T20:00:00Z", "time_zone": "UTC"},
        end={"date_time": "2030-01-07T21:00:00Z", "time_zone": "UTC"},
    )
    result = write.record_outcome(
        receipt.intent_id, "stale_precondition", confirmed=google
    )
    # Ordinary drift: resolved automatically, never surfaced.
    assert result.rebased is True
    assert result.recovery is None
    assert result.state == "ready"
    assert overlay_for(engine)[1] == []

    plans = write.select_provider_work().plans
    assert plans[0].expected_provider_etag == '"etag-moved"'
    assert plans[0].changed_fields == ["title"]  # only the human's own field
    assert overlay_for(engine)[0] == {"title": "B"}


# --- 6. Same-field drift ----------------------------------------------------


def test_same_field_drift_lets_the_pending_human_value_win_this_cycle(tmp_path):
    write, engine = coordinator(tmp_path)
    receipt = write.accept_direct_human_intent(
        BLOCK_ID, edit("B", "11111111-1111-4111-8111-111111111111")
    )
    write.begin_attempt(receipt.intent_id)
    result = write.record_outcome(
        receipt.intent_id, "stale_precondition", confirmed=confirmed('"e-x"', title="X")
    )
    assert result.rebased is True and result.recovery is None
    # The base adopts X, but the pending human intent still owns `title`.
    with engine.begin() as connection:
        row = connection.execute(select(calendar_provider_write_intents)).one()
    assert json.loads(row.base_values_json)["title"] == "X"
    assert json.loads(row.desired_values_json)["title"] == "B"
    assert overlay_for(engine)[0] == {"title": "B"}

    write.begin_attempt(receipt.intent_id)
    write.record_outcome(receipt.intent_id, "success", confirmed=confirmed('"e2"', "B"))
    assert block_title(engine) == "B"
    # Ownership ends at confirmation: a later Google value flows in normally.
    assert pending_changed_fields_for(engine) == set()


def pending_changed_fields_for(engine, block_id=BLOCK_ID):
    with engine.connect() as connection:
        return pending_changed_fields(connection, block_id)


# --- 7. Read sync during a pending intent -----------------------------------


def test_read_sync_may_not_overwrite_a_pending_human_field(tmp_path):
    write, engine = coordinator(tmp_path)
    write.accept_direct_human_intent(
        BLOCK_ID, edit("B", "11111111-1111-4111-8111-111111111111")
    )
    owned = pending_changed_fields_for(engine)
    assert owned == {"title"}
    # Untouched fields are not owned, so Google may refresh them freely.
    assert "start" not in owned and "end" not in owned
    # And no review state is produced by any of it.
    assert overlay_for(engine)[1] == []


# --- 9. Exception: provider target deleted ----------------------------------


def test_a_deleted_provider_target_is_a_named_condition_not_a_review(tmp_path):
    write, engine = coordinator(tmp_path)
    receipt = write.accept_direct_human_intent(
        BLOCK_ID, edit("B", "11111111-1111-4111-8111-111111111111")
    )
    write.begin_attempt(receipt.intent_id)
    result = write.record_outcome(receipt.intent_id, "provider_not_found")
    assert result.recovery == "provider_target_deleted"
    assert result.state == "failed"

    _, recovery = overlay_for(engine)
    assert [entry["kind"] for entry in recovery] == ["provider_target_deleted"]


def test_structural_change_during_a_rebase_stops_honestly(tmp_path):
    """A version difference is ordinary; a structural change is not."""

    write, engine = coordinator(tmp_path)
    receipt = write.accept_direct_human_intent(
        BLOCK_ID, edit("B", "11111111-1111-4111-8111-111111111111")
    )
    write.begin_attempt(receipt.intent_id)
    result = write.record_outcome(
        receipt.intent_id,
        "stale_precondition",
        confirmed=confirmed('"e2"', "B", recurring=True),
    )
    assert result.rebased is False
    assert result.recovery == "recurrence_identity_lost"
    _, recovery = overlay_for(engine)
    assert [entry["kind"] for entry in recovery] == ["recurrence_identity_lost"]


def test_no_ordinary_r1_path_produces_a_generic_review_state(tmp_path):
    """The whole R1 happy path, asserting the owner is never asked anything."""

    write, engine = coordinator(tmp_path)
    first = write.accept_direct_human_intent(
        BLOCK_ID, edit("B", "11111111-1111-4111-8111-111111111111")
    )
    write.begin_attempt(first.intent_id)
    second = write.accept_direct_human_intent(
        BLOCK_ID, edit("C", "22222222-2222-4222-8222-222222222222")
    )
    write.record_outcome(
        first.intent_id, "stale_precondition", confirmed=confirmed('"e2"', "A")
    )
    write.recover()
    for _ in range(3):
        work = write.select_provider_work()
        if not work.plans:
            break
        plan = work.plans[0]
        write.begin_attempt(plan.intent_id)
        write.record_outcome(
            plan.intent_id, "success", confirmed=confirmed('"e-final"', "C")
        )
        _, recovery = overlay_for(engine)
        assert recovery == []

    assert block_title(engine) == "C"
    assert overlay_for(engine) == ({}, [])
    with engine.begin() as connection:
        states = {
            row.state
            for row in connection.execute(select(calendar_provider_write_intents))
        }
    assert "conflict" not in states
    assert second.intent_id is not None
