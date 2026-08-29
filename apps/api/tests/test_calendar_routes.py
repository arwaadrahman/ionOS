from uuid import uuid4

from fastapi.testclient import TestClient

from ion_api.calendar_contracts import CALENDAR_LIST_SCOPE, EVENTS_READ_SCOPE
from ion_api.main import create_production_app
from ion_api.migrations import upgrade_to_head
from ion_api.settings import Settings

TOKEN = "synthetic-session-token"
HEADERS = {"X-Ion-Session": TOKEN}


def connect_payload():
    return {
        "provider_account_id": "synthetic-primary@example.invalid",
        "display_name": "Synthetic Calendar Account",
        "granted_scopes": [CALENDAR_LIST_SCOPE, EVENTS_READ_SCOPE],
        "keychain_locator": "ion-google-synthetic-locator",
        "calendars": [
            {
                "provider_calendar_id": "synthetic-primary@example.invalid",
                "summary": "Synthetic Primary Calendar",
                "timezone": "America/Los_Angeles",
                "access_role": "owner",
                "is_primary": True,
                "provider_selected": True,
            }
        ],
    }


def test_fixed_calendar_routes_require_local_session_and_hide_keychain_locator(
    tmp_path,
):
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    with TestClient(create_production_app(settings, TOKEN)) as client:
        assert client.get("/v1/calendar/status").status_code == 401
        connected = client.post(
            "/v1/calendar/accounts/connect",
            headers=HEADERS,
            json=connect_payload(),
        )
        assert connected.status_code == 200
        public = connected.json()
        serialized = connected.text
        assert public["accounts"][0]["auth_state"] == "connected"
        assert "keychain_locator" not in serialized
        assert "synthetic-locator" not in serialized
        assert "refresh_token" not in serialized
        assert "access_token" not in serialized

        internal = client.post("/v1/calendar/internal/state", headers=HEADERS, json={})
        assert internal.status_code == 200
        assert (
            internal.json()["accounts"][0]["keychain_locator"]
            == "ion-google-synthetic-locator"
        )
        assert "refresh_token" not in internal.text
        assert "access_token" not in internal.text


def test_selection_and_disconnect_are_revisioned_fixed_mutations(tmp_path):
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    with TestClient(create_production_app(settings, TOKEN)) as client:
        status = client.post(
            "/v1/calendar/accounts/connect",
            headers=HEADERS,
            json=connect_payload(),
        ).json()
        calendar = status["calendars"][0]
        changed = client.put(
            f"/v1/calendar/calendars/{calendar['id']}/selection",
            headers=HEADERS,
            json={"enabled": False, "expected_revision": calendar["revision"]},
        )
        assert changed.status_code == 200
        assert changed.json()["calendars"][0]["enabled_in_ion"] is False

        stale = client.put(
            f"/v1/calendar/calendars/{calendar['id']}/selection",
            headers=HEADERS,
            json={"enabled": True, "expected_revision": calendar["revision"]},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "revision_conflict"

        account_id = status["accounts"][0]["id"]
        disconnected = client.post(
            f"/v1/calendar/accounts/{account_id}/disconnect",
            headers=HEADERS,
            json={},
        )
        assert disconnected.status_code == 200
        assert disconnected.json()["accounts"][0]["auth_state"] == "disconnected"


def test_fixed_sync_routes_advance_success_and_cache_canonical_blocks(tmp_path):
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    with TestClient(create_production_app(settings, TOKEN)) as client:
        status = client.post(
            "/v1/calendar/accounts/connect",
            headers=HEADERS,
            json=connect_payload(),
        ).json()
        calendar_id = status["calendars"][0]["id"]
        generation = str(uuid4())
        route = f"/v1/calendar/calendars/{calendar_id}/sync"

        assert (
            client.post(
                f"{route}/begin",
                headers=HEADERS,
                json={"generation": generation, "mode": "full"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"{route}/page",
                headers=HEADERS,
                json={
                    "generation": generation,
                    "events": [
                        {
                            "provider_event_id": "synthetic-event",
                            "ical_uid": "synthetic-event@example.invalid",
                            "provider_etag": '"synthetic-v1"',
                            "provider_updated_at": "2030-03-01T12:00:00Z",
                            "title": "Synthetic Calendar Event",
                            "status": "confirmed",
                            "transparency": "opaque",
                            "start": {
                                "date_time": "2030-03-10T09:00:00-07:00",
                                "timezone": "America/Los_Angeles",
                            },
                            "end": {
                                "date_time": "2030-03-10T10:00:00-07:00",
                                "timezone": "America/Los_Angeles",
                            },
                        }
                    ],
                },
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"{route}/complete",
                headers=HEADERS,
                json={
                    "generation": generation,
                    "next_sync_token": "synthetic-next-sync-token",
                },
            ).status_code
            == 200
        )

        synced = client.get("/v1/calendar/status", headers=HEADERS).json()
        assert synced["calendars"][0]["sync_state"] == "idle"
        assert synced["calendars"][0]["last_synced_at"] is not None
        assert synced["calendars"][0]["has_sync_token"] is True
        assert len(synced["blocks"]) == 1
        assert synced["blocks"][0]["provider_event_id"] == "synthetic-event"

        legacy = client.post(
            f"/v1/calendar/{calendar_id}/sync/begin",
            headers=HEADERS,
            json={"generation": str(uuid4()), "mode": "full"},
        )
        assert legacy.status_code == 404


def test_provider_failure_reason_is_persisted_as_safe_allowlisted_metadata(tmp_path):
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    with TestClient(create_production_app(settings, TOKEN)) as client:
        status = client.post(
            "/v1/calendar/accounts/connect",
            headers=HEADERS,
            json=connect_payload(),
        ).json()
        calendar_id = status["calendars"][0]["id"]
        route = f"/v1/calendar/calendars/{calendar_id}/sync"

        assert (
            client.post(
                f"{route}/begin",
                headers=HEADERS,
                json={"generation": str(uuid4()), "mode": "full"},
            ).status_code
            == 200
        )
        assert (
            client.post(
                f"{route}/failure",
                headers=HEADERS,
                json={
                    "error_code": "provider_not_found",
                    "retry_count": 0,
                    "next_retry_at": None,
                },
            ).status_code
            == 200
        )

        failed = client.get("/v1/calendar/status", headers=HEADERS).json()
        calendar = failed["calendars"][0]
        assert calendar["sync_state"] == "failed"
        assert calendar["last_error_code"] == "provider_not_found"
        assert calendar["last_synced_at"] is None
