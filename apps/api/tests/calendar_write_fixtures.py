"""Synthetic write-eligible Calendar fixtures shared by the R0 test suites.

Entirely synthetic: no real account, calendar, event, or provider identifier.
"""

from __future__ import annotations

from sqlalchemy import Engine, insert

from ion_api.schema import (
    calendar_blocks,
    google_accounts,
    google_calendars,
    google_event_links,
)

ACCOUNT_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
CALENDAR_ID = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
BLOCK_ID = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
NOW = "2030-01-07T00:00:00Z"


def seed_writable_event(
    engine: Engine,
    *,
    write_granted: bool = True,
    access_role: str = "owner",
    has_attendees: bool = False,
    provider_locked: bool = False,
    provider_event_type: str = "default",
    link_state: str = "confirmed",
    block_id: str = BLOCK_ID,
) -> None:
    with engine.begin() as connection:
        existing = connection.execute(google_accounts.select()).first()
        if existing is None:
            connection.execute(
                insert(google_accounts).values(
                    id=ACCOUNT_ID,
                    provider_account_id="synthetic-primary@example.invalid",
                    display_name="Synthetic Calendar Account",
                    granted_scopes="[]",
                    keychain_locator="ion-google-synthetic-r0",
                    auth_state="connected",
                    created_at=NOW,
                    updated_at=NOW,
                    revision=1,
                    calendar_write_scope_state=(
                        "write_granted" if write_granted else "read_only"
                    ),
                )
            )
            connection.execute(
                insert(google_calendars).values(
                    id=CALENDAR_ID,
                    account_id=ACCOUNT_ID,
                    provider_calendar_id="synthetic-primary@example.invalid",
                    summary="Synthetic Primary Calendar",
                    timezone="America/Los_Angeles",
                    access_role=access_role,
                    is_primary=1,
                    provider_selected=1,
                    enabled_in_ion=1,
                    sync_state="idle",
                    created_at=NOW,
                    updated_at=NOW,
                    revision=1,
                )
            )
        connection.execute(
            insert(calendar_blocks).values(
                id=block_id,
                source_kind="google",
                title="Synthetic study block",
                temporal_kind="timed",
                start_at="2030-01-07T17:00:00Z",
                end_at="2030-01-07T18:00:00Z",
                start_timezone="America/Los_Angeles",
                end_timezone="America/Los_Angeles",
                status="confirmed",
                transparency="opaque",
                recurrence_kind="single",
                created_at=NOW,
                updated_at=NOW,
                revision=1,
            )
        )
        connection.execute(
            insert(google_event_links).values(
                calendar_block_id=block_id,
                account_id=ACCOUNT_ID,
                calendar_id=CALENDAR_ID,
                provider_event_id=f"synthetic-event-{block_id[:8]}",
                provider_etag='"synthetic-etag-1"',
                original_start_kind="none",
                last_seen_sync_generation="11111111-1111-4111-8111-111111111111",
                link_state=link_state,
                provider_event_type=provider_event_type,
                provider_locked=provider_locked,
                has_attendees=has_attendees,
            )
        )


def intent_payload(**overrides) -> dict:
    payload = {
        "command_id": "11111111-1111-4111-8111-111111111111",
        "operation": "patch",
        "recurrence_scope": "single",
        "expected_revision": 1,
        "changed_fields": ["title"],
        "draft": {"title": "Renamed study block"},
        "provenance": "direct_human",
    }
    payload.update(overrides)
    return payload
