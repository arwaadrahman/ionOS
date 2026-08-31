from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import select, update

from ion_api.calendar import CalendarService
from ion_api.calendar_contracts import (
    CALENDAR_LIST_SCOPE,
    EVENTS_READ_SCOPE,
    CalendarCategoryInput,
    CalendarVisibilityInput,
    GoogleAccountConnectInput,
    ProviderCalendarInput,
    ProviderDateTime,
    ProviderEventInput,
    SelectionInput,
    SyncBeginInput,
    SyncCompleteInput,
    SyncFailureInput,
    SyncPageInput,
)
from ion_api.db import create_database_engine
from ion_api.migrations import upgrade_to_head
from ion_api.schema import audit_events, calendar_block_ion_metadata
from ion_api.settings import Settings


def provider_calendar(**overrides):
    values = {
        "provider_calendar_id": "synthetic-primary@example.invalid",
        "summary": "Synthetic Primary Calendar",
        "description": None,
        "location": None,
        "timezone": "America/Los_Angeles",
        "access_role": "owner",
        "provider_etag": '"calendar-v1"',
        "is_primary": True,
        "provider_selected": True,
        "provider_hidden": False,
        "provider_deleted": False,
    }
    values.update(overrides)
    return ProviderCalendarInput.model_validate(values)


def test_calendar_category_contract_is_two_level_and_extensible():
    future = CalendarCategoryInput(
        category="personal_project",
        category_subtype="future_extension_2",
        expected_revision=1,
    )
    assert future.category_subtype == "future_extension_2"
    with pytest.raises(ValidationError):
        CalendarCategoryInput(
            category=None,
            category_subtype="homework_study",
            expected_revision=1,
        )
    with pytest.raises(ValidationError):
        CalendarCategoryInput(
            category="academic",
            category_subtype="Invalid subtype",
            expected_revision=1,
        )
    with pytest.raises(ValidationError):
        CalendarCategoryInput(
            category="career",
            category_subtype=None,
            expected_revision=1,
        )
    assert (
        CalendarCategoryInput(
            category="ion_focus",
            category_subtype=None,
            expected_revision=1,
        ).category
        == "ion_focus"
    )


def connected_service(tmp_path):
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    engine = create_database_engine(settings.database_path)
    service = CalendarService(engine)
    service.connect_account(
        GoogleAccountConnectInput(
            provider_account_id="synthetic-primary@example.invalid",
            display_name="Synthetic Calendar Account",
            granted_scopes=[EVENTS_READ_SCOPE, CALENDAR_LIST_SCOPE],
            keychain_locator="ion-google-synthetic-locator",
            calendars=[
                provider_calendar(),
                provider_calendar(
                    provider_calendar_id="synthetic-hidden@example.invalid",
                    summary="Synthetic Hidden Calendar",
                    is_primary=False,
                    provider_selected=False,
                    provider_hidden=True,
                ),
            ],
        )
    )
    return service, engine


def timed(value: str, timezone: str = "America/Los_Angeles"):
    return ProviderDateTime(date_time=value, timezone=timezone)


def all_day(value: str):
    return ProviderDateTime(date=value)


def event(event_id: str, **overrides):
    values = {
        "provider_event_id": event_id,
        "ical_uid": f"{event_id}@example.invalid",
        "provider_etag": f'"{event_id}-v1"',
        "provider_updated_at": "2030-03-01T12:00:00Z",
        "title": f"Synthetic {event_id}",
        "status": "confirmed",
        "transparency": "opaque",
        "start": timed("2030-03-10T01:30:00-08:00"),
        "end": timed("2030-03-10T03:30:00-07:00"),
    }
    values.update(overrides)
    return ProviderEventInput.model_validate(values)


def test_all_starter_categories_round_trip_restart_and_reconciliation(tmp_path):
    service, engine = connected_service(tmp_path)
    calendar = service.status().calendars[0]
    starter_categories = [
        ("academic", "class_section"),
        ("academic", "homework_study"),
        ("academic", "quiz_exam"),
        ("career", "internship_recruiting"),
        ("career", "application_admin"),
        ("career", "interview_networking"),
        ("personal_project", "build"),
        ("personal_project", "research"),
        ("personal_project", "creative"),
        ("routine_physical", "work_shift"),
        ("routine_physical", "meal"),
        ("routine_physical", "gym"),
        ("routine_physical", "hygiene"),
        ("routine_physical", "chores_errands"),
        ("personal", "appointment"),
        ("personal", "family"),
        ("personal", "travel"),
        ("personal", "personal_admin"),
        ("fun", "social"),
        ("fun", "entertainment"),
        ("fun", "gaming_media"),
        ("fun", "leisure"),
        ("ion_focus", None),
    ]
    provider_events = [
        event(f"category-{index}") for index in range(len(starter_categories))
    ]
    provider_events.append(event("uncategorized"))
    generation = str(uuid4())
    service.begin_sync(calendar.id, SyncBeginInput(generation=generation, mode="full"))
    service.apply_sync_page(
        calendar.id,
        SyncPageInput(generation=generation, events=provider_events),
    )
    service.complete_sync(
        calendar.id,
        SyncCompleteInput(generation=generation, next_sync_token="category-token-1"),
    )

    blocks = {item.provider_event_id: item for item in service.status().blocks}
    for index, (category, subtype) in enumerate(starter_categories):
        block_id = f"category-{index}"
        service.set_category(
            blocks[block_id].id,
            CalendarCategoryInput(
                category=category,
                category_subtype=subtype,
                expected_revision=1,
            ),
        )

    restarted = CalendarService(engine)
    restarted_blocks = {
        item.provider_event_id: item for item in restarted.status().blocks
    }
    for index, expected in enumerate(starter_categories):
        block = restarted_blocks[f"category-{index}"]
        assert (block.category, block.category_subtype) == expected
    uncategorized = restarted_blocks["uncategorized"]
    assert (uncategorized.category, uncategorized.category_subtype) == (None, None)

    generation = str(uuid4())
    restarted.begin_sync(
        calendar.id, SyncBeginInput(generation=generation, mode="incremental")
    )
    restarted.apply_sync_page(
        calendar.id,
        SyncPageInput(
            generation=generation,
            events=[
                event(
                    item.provider_event_id, title=f"Reconciled {item.provider_event_id}"
                )
                for item in provider_events
            ],
        ),
    )
    restarted.complete_sync(
        calendar.id,
        SyncCompleteInput(generation=generation, next_sync_token="category-token-2"),
    )
    reconciled = {item.provider_event_id: item for item in restarted.status().blocks}
    for index, expected in enumerate(starter_categories):
        block = reconciled[f"category-{index}"]
        assert (block.category, block.category_subtype) == expected


def test_contract_requires_exact_read_only_scopes_and_explicit_temporal_union():
    with pytest.raises(ValidationError):
        GoogleAccountConnectInput(
            provider_account_id="synthetic@example.invalid",
            display_name="Synthetic",
            granted_scopes=["https://www.googleapis.com/auth/calendar"],
            keychain_locator="ion-google-synthetic-locator",
            calendars=[provider_calendar()],
        )
    with pytest.raises(ValidationError):
        ProviderDateTime(date="2030-01-01", date_time="2030-01-01T00:00:00Z")
    with pytest.raises(ValidationError):
        ProviderDateTime(date_time="2030-01-01T00:00:00Z", timezone="Not/AZone")


def test_discovery_defaults_and_ion_selection_are_independent(tmp_path):
    service, _ = connected_service(tmp_path)
    status = service.status()
    assert len(status.accounts) == 1
    assert not hasattr(status.accounts[0], "keychain_locator")
    primary, hidden = status.calendars
    assert primary.enabled_in_ion is True
    assert primary.hidden_in_ion is False
    assert hidden.enabled_in_ion is False
    assert hidden.provider_hidden is True

    changed = service.set_selection(
        hidden.id,
        SelectionInput(enabled=True, expected_revision=hidden.revision),
    )
    selected = next(item for item in changed.calendars if item.id == hidden.id)
    assert selected.enabled_in_ion is True
    assert selected.provider_hidden is True

    hidden_locally = service.set_visibility(
        selected.id,
        CalendarVisibilityInput(hidden=True, expected_revision=selected.revision),
    )
    selected = next(item for item in hidden_locally.calendars if item.id == hidden.id)
    assert selected.hidden_in_ion is True

    rediscovered = service.connect_account(
        GoogleAccountConnectInput(
            provider_account_id="synthetic-primary@example.invalid",
            display_name="Synthetic Calendar Account",
            granted_scopes=[CALENDAR_LIST_SCOPE, EVENTS_READ_SCOPE],
            keychain_locator="ion-google-synthetic-locator",
            calendars=[
                provider_calendar(provider_selected=False),
                provider_calendar(
                    provider_calendar_id="synthetic-hidden@example.invalid",
                    summary="Synthetic Hidden Calendar",
                    is_primary=False,
                    provider_selected=False,
                    provider_hidden=True,
                ),
            ],
        )
    )
    selected = next(item for item in rediscovered.calendars if item.id == hidden.id)
    assert selected.enabled_in_ion is True
    assert selected.hidden_in_ion is True
    assert selected.provider_selected is False


def test_calendar_list_reconciliation_retires_stale_rows_without_losing_identity(
    tmp_path,
):
    service, _ = connected_service(tmp_path)
    initial = service.status()
    secondary = next(
        item
        for item in initial.calendars
        if item.provider_calendar_id == "synthetic-hidden@example.invalid"
    )
    selected = service.set_selection(
        secondary.id,
        SelectionInput(enabled=True, expected_revision=secondary.revision),
    )
    secondary = next(item for item in selected.calendars if item.id == secondary.id)
    generation = str(uuid4())
    service.begin_sync(secondary.id, SyncBeginInput(generation=generation, mode="full"))
    service.apply_sync_page(
        secondary.id,
        SyncPageInput(generation=generation, events=[event("retained-event")]),
    )
    service.complete_sync(
        secondary.id,
        SyncCompleteInput(generation=generation, next_sync_token="retained-token"),
    )
    retained_block = next(
        item
        for item in service.status().blocks
        if item.provider_event_id == "retained-event"
    )
    service.set_category(
        retained_block.id,
        CalendarCategoryInput(
            category="personal_project",
            category_subtype="build",
            expected_revision=retained_block.ion_metadata_revision,
        ),
    )

    removed = service.connect_account(
        GoogleAccountConnectInput(
            provider_account_id="synthetic-primary@example.invalid",
            display_name="Synthetic Calendar Account",
            granted_scopes=[CALENDAR_LIST_SCOPE, EVENTS_READ_SCOPE],
            keychain_locator="ion-google-reconnected-locator",
            calendars=[provider_calendar(summary="Renamed Synthetic Primary")],
        )
    )
    stale = next(item for item in removed.calendars if item.id == secondary.id)
    assert stale.provider_deleted is True
    assert stale.enabled_in_ion is False
    assert stale.summary == "Synthetic Hidden Calendar"
    preserved = next(
        item for item in removed.blocks if item.provider_event_id == "retained-event"
    )
    assert preserved.calendar_id == secondary.id
    assert (preserved.category, preserved.category_subtype) == (
        "personal_project",
        "build",
    )

    tombstoned = service.connect_account(
        GoogleAccountConnectInput(
            provider_account_id="synthetic-primary@example.invalid",
            display_name="Synthetic Calendar Account",
            granted_scopes=[CALENDAR_LIST_SCOPE, EVENTS_READ_SCOPE],
            keychain_locator="ion-google-reconnected-locator",
            calendars=[
                provider_calendar(summary="Renamed Synthetic Primary"),
                provider_calendar(
                    provider_calendar_id="synthetic-hidden@example.invalid",
                    summary=None,
                    is_primary=False,
                    provider_selected=False,
                    provider_deleted=True,
                ),
                provider_calendar(
                    provider_calendar_id="unknown-deleted@example.invalid",
                    summary=None,
                    is_primary=False,
                    provider_selected=False,
                    provider_deleted=True,
                ),
            ],
        )
    )
    stale = next(item for item in tombstoned.calendars if item.id == secondary.id)
    assert stale.summary == "Synthetic Hidden Calendar"
    assert not any(
        item.provider_calendar_id == "unknown-deleted@example.invalid"
        for item in tombstoned.calendars
    )

    restored = service.connect_account(
        GoogleAccountConnectInput(
            provider_account_id="synthetic-primary@example.invalid",
            display_name="Synthetic Calendar Account",
            granted_scopes=[CALENDAR_LIST_SCOPE, EVENTS_READ_SCOPE],
            keychain_locator="ion-google-reconnected-locator",
            calendars=[
                provider_calendar(summary="Renamed Synthetic Primary"),
                provider_calendar(
                    provider_calendar_id="synthetic-hidden@example.invalid",
                    summary="Restored Provider Title",
                    is_primary=False,
                    provider_selected=True,
                    provider_deleted=False,
                ),
                provider_calendar(
                    provider_calendar_id="genuinely-unnamed@example.invalid",
                    summary=None,
                    is_primary=False,
                    provider_selected=True,
                    provider_deleted=False,
                ),
            ],
        )
    )
    matching = [
        item
        for item in restored.calendars
        if item.provider_calendar_id == "synthetic-hidden@example.invalid"
    ]
    assert len(matching) == 1
    assert matching[0].id == secondary.id
    assert matching[0].summary == "Restored Provider Title"
    assert matching[0].provider_deleted is False
    unnamed = next(
        item
        for item in restored.calendars
        if item.provider_calendar_id == "genuinely-unnamed@example.invalid"
    )
    assert unnamed.summary == "Untitled Google Calendar"


def test_full_and_incremental_sync_preserve_identity_recurrence_and_audit(tmp_path):
    service, engine = connected_service(tmp_path)
    calendar = service.status().calendars[0]
    generation = str(uuid4())
    service.begin_sync(calendar.id, SyncBeginInput(generation=generation, mode="full"))
    shared_uid = "shared-synthetic@example.invalid"
    master = event(
        "master-event",
        recurrence=["RRULE:FREQ=WEEKLY;COUNT=4"],
        start=timed("2030-03-04T09:00:00-08:00"),
        end=timed("2030-03-04T10:00:00-08:00"),
    )
    moved = event(
        "moved-exception",
        recurring_event_id="master-event",
        original_start=timed("2030-03-11T09:00:00-07:00"),
        start=timed("2030-03-11T13:00:00-07:00"),
        end=timed("2030-03-11T14:00:00-07:00"),
    )
    cancelled = event(
        "cancelled-exception",
        title=None,
        status="cancelled",
        start=None,
        end=None,
        recurring_event_id="master-event",
        original_start=timed("2030-03-18T09:00:00-07:00"),
    )
    items = [
        event("event-a", ical_uid=shared_uid),
        event("event-b", ical_uid=shared_uid),
        event(
            "all-day",
            start=all_day("2030-03-20"),
            end=all_day("2030-03-22"),
        ),
        master,
        moved,
        cancelled,
    ]
    # The first full sync can apply any number of provider pages before the token.
    service.apply_sync_page(
        calendar.id, SyncPageInput(generation=generation, events=items[:3])
    )
    service.apply_sync_page(
        calendar.id, SyncPageInput(generation=generation, events=items[3:])
    )
    # Replaying the same provider page is duplicate-safe and writes no block revision.
    service.apply_sync_page(
        calendar.id, SyncPageInput(generation=generation, events=items)
    )
    service.complete_sync(
        calendar.id,
        SyncCompleteInput(generation=generation, next_sync_token="sync-token-1"),
    )

    status = service.status()
    assert len(status.blocks) == 6
    by_event = {item.provider_event_id: item for item in status.blocks}
    assert by_event["event-a"].id != by_event["event-b"].id
    assert by_event["event-a"].ical_uid == by_event["event-b"].ical_uid
    assert by_event["event-a"].start_timezone == "America/Los_Angeles"
    assert by_event["event-a"].end_at == "2030-03-10T03:30:00-07:00"
    assert by_event["all-day"].temporal_kind == "all_day"
    assert by_event["all-day"].start_date == "2030-03-20"
    assert by_event["all-day"].end_date == "2030-03-22"
    assert by_event["master-event"].recurrence_kind == "master"
    assert (
        by_event["moved-exception"].recurrence_master_block_id
        == by_event["master-event"].id
    )
    assert by_event["moved-exception"].original_start_kind == "instant"
    assert by_event["moved-exception"].original_start_at == "2030-03-11T09:00:00-07:00"
    assert by_event["moved-exception"].original_start_timezone == "America/Los_Angeles"
    assert by_event["cancelled-exception"].status == "cancelled"
    assert by_event["cancelled-exception"].start_at == "2030-03-18T09:00:00-07:00"
    assert by_event["cancelled-exception"].original_start_kind == "instant"
    assert all(item.revision == 1 for item in status.blocks)

    with engine.connect() as connection:
        events = connection.execute(
            select(audit_events).where(audit_events.c.entity_type == "calendar_block")
        ).all()
    assert len(events) == 6
    assert {item.actor_kind for item in events} == {"integration"}
    assert {item.authority for item in events} == {"automated"}
    assert all(item.source == "google_calendar" for item in events)

    with engine.begin() as connection:
        connection.execute(
            update(calendar_block_ion_metadata)
            .where(
                calendar_block_ion_metadata.c.calendar_block_id
                == by_event["event-a"].id
            )
            .values(flexibility="flexible", notes="Synthetic Ion-only note")
        )

    categorized = service.set_category(
        by_event["event-a"].id,
        CalendarCategoryInput(
            category="academic",
            category_subtype="homework_study",
            expected_revision=by_event["event-a"].ion_metadata_revision,
        ),
    )
    categorized_event = next(
        item for item in categorized.blocks if item.provider_event_id == "event-a"
    )
    assert categorized_event.category == "academic"
    assert categorized_event.category_subtype == "homework_study"
    assert categorized_event.ion_metadata_revision == 2

    incremental = str(uuid4())
    service.begin_sync(
        calendar.id, SyncBeginInput(generation=incremental, mode="incremental")
    )
    service.apply_sync_page(
        calendar.id,
        SyncPageInput(
            generation=incremental,
            events=[
                event(
                    "event-a",
                    ical_uid=shared_uid,
                    provider_etag='"event-a-v2"',
                    title="Synthetic Event A Updated",
                ),
                ProviderEventInput(
                    provider_event_id="event-b",
                    status="cancelled",
                ),
            ],
        ),
    )
    service.complete_sync(
        calendar.id,
        SyncCompleteInput(generation=incremental, next_sync_token="sync-token-2"),
    )
    by_event = {item.provider_event_id: item for item in service.status().blocks}
    assert by_event["event-a"].title == "Synthetic Event A Updated"
    assert by_event["event-a"].flexibility == "flexible"
    assert by_event["event-a"].notes == "Synthetic Ion-only note"
    assert by_event["event-a"].category == "academic"
    assert by_event["event-a"].category_subtype == "homework_study"
    assert by_event["event-a"].ion_metadata_revision == 2
    assert by_event["event-b"].status == "cancelled"
    assert by_event["event-b"].provider_deleted_at is not None


def test_full_resync_marks_unseen_without_losing_cached_or_ion_owned_state(tmp_path):
    service, engine = connected_service(tmp_path)
    calendar = service.status().calendars[0]
    first = str(uuid4())
    service.begin_sync(calendar.id, SyncBeginInput(generation=first, mode="full"))
    service.apply_sync_page(
        calendar.id,
        SyncPageInput(generation=first, events=[event("kept"), event("removed")]),
    )
    service.complete_sync(
        calendar.id, SyncCompleteInput(generation=first, next_sync_token="old-token")
    )
    removed = next(
        item for item in service.status().blocks if item.provider_event_id == "removed"
    )
    with engine.begin() as connection:
        connection.execute(
            update(calendar_block_ion_metadata)
            .where(calendar_block_ion_metadata.c.calendar_block_id == removed.id)
            .values(notes="Preserved synthetic metadata")
        )

    reset = str(uuid4())
    service.begin_sync(calendar.id, SyncBeginInput(generation=reset, mode="full"))
    service.apply_sync_page(
        calendar.id, SyncPageInput(generation=reset, events=[event("kept")])
    )
    service.complete_sync(
        calendar.id, SyncCompleteInput(generation=reset, next_sync_token="new-token")
    )
    offline = service.status()
    removed = next(
        item for item in offline.blocks if item.provider_event_id == "removed"
    )
    assert removed.status == "cancelled"
    assert removed.notes == "Preserved synthetic metadata"
    assert offline.calendars[0].has_sync_token is True

    service.fail_sync(
        calendar.id,
        SyncFailureInput(
            error_code="network",
            retry_count=2,
            next_retry_at="2030-03-01T12:05:00Z",
        ),
    )
    cached = service.status()
    assert len(cached.blocks) == 2
    assert cached.calendars[0].sync_state == "retry_wait"
    assert cached.calendars[0].last_error_code == "network"
    assert cached.calendars[0].next_retry_at is not None

    service.fail_sync(
        calendar.id,
        SyncFailureInput(
            error_code="reauth_required", retry_count=0, next_retry_at=None
        ),
    )
    reauth = service.status()
    assert reauth.accounts[0].auth_state == "reauth_required"
    assert reauth.calendars[0].sync_state == "reauth_required"

    disconnected = service.disconnect_account(reauth.accounts[0].id)
    assert disconnected.accounts[0].auth_state == "disconnected"
    assert all(item.sync_state == "disconnected" for item in disconnected.calendars)
    assert len(disconnected.blocks) == 2
