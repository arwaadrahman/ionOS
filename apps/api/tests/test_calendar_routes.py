import re
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

from ion_api.calendar_contracts import (
    CALENDAR_LIST_SCOPE,
    EVENTS_READ_SCOPE,
    EVENTS_WRITE_SCOPE,
)
from ion_api.calendar_routes import SAFE_CALENDAR_WRITE_REASONS
from ion_api.calendar_writes import MAX_AUTOMATIC_ATTEMPTS
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

        visible_revision = changed.json()["calendars"][0]["revision"]
        hidden = client.put(
            f"/v1/calendar/calendars/{calendar['id']}/visibility",
            headers=HEADERS,
            json={"hidden": True, "expected_revision": visible_revision},
        )
        assert hidden.status_code == 200
        assert hidden.json()["calendars"][0]["hidden_in_ion"] is True

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

        block = synced["blocks"][0]
        categorized = client.put(
            f"/v1/calendar/blocks/{block['id']}/category",
            headers=HEADERS,
            json={
                "category": "academic",
                "category_subtype": "quiz_exam",
                "expected_revision": block["ion_metadata_revision"],
            },
        )
        assert categorized.status_code == 200
        categorized_block = categorized.json()["blocks"][0]
        assert categorized_block["category"] == "academic"
        assert categorized_block["category_subtype"] == "quiz_exam"
        assert categorized_block["ion_metadata_revision"] == 2

        rejected = client.put(
            f"/v1/calendar/blocks/{block['id']}/category",
            headers=HEADERS,
            json={"category": "provider-write", "expected_revision": 2},
        )
        assert rejected.status_code == 422

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


def test_recurrence_unsupported_survives_domain_error_to_http_safe_detail(tmp_path):
    """A known safe reason (recurrence_unsupported) must reach the HTTP
    response `reason` field rather than silently degrading to the generic
    validation detail. This guards the route-level `_raise_safe` allowlist
    against a newly introduced safe reason being forgotten there."""
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    with TestClient(create_production_app(settings, TOKEN)) as client:
        payload = connect_payload()
        payload["granted_scopes"] = [CALENDAR_LIST_SCOPE, EVENTS_WRITE_SCOPE]
        status = client.post(
            "/v1/calendar/accounts/connect", headers=HEADERS, json=payload
        ).json()
        calendar_id = status["calendars"][0]["id"]
        generation = str(uuid4())
        route = f"/v1/calendar/calendars/{calendar_id}/sync"
        client.post(
            f"{route}/begin",
            headers=HEADERS,
            json={"generation": generation, "mode": "full"},
        )
        client.post(
            f"{route}/page",
            headers=HEADERS,
            json={
                "generation": generation,
                "events": [
                    {
                        "provider_event_id": "synthetic-recurring-event",
                        "ical_uid": "synthetic-recurring-event@example.invalid",
                        "provider_etag": '"synthetic-v1"',
                        "provider_updated_at": "2030-03-01T12:00:00Z",
                        "title": "Synthetic Weekly Event",
                        "status": "confirmed",
                        "transparency": "opaque",
                        "recurrence": ["RRULE:FREQ=WEEKLY"],
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
        )
        client.post(
            f"{route}/complete",
            headers=HEADERS,
            json={"generation": generation, "next_sync_token": "synthetic-sync"},
        )
        block = client.get("/v1/calendar/status", headers=HEADERS).json()["blocks"][0]
        assert block["recurrence_kind"] == "master"

        rejected = client.post(
            "/v1/calendar/internal/write-intents",
            headers=HEADERS,
            json={
                "command_id": str(uuid4()),
                "calendar_block_id": block["id"],
                "operation": "patch",
                "recurrence_scope": "single",
                "changed_fields": ["title"],
                "base_values": {"title": "Synthetic Weekly Event"},
                "desired_values": {"title": "Renamed"},
                "expected_block_revision": block["revision"],
            },
        )
        assert rejected.status_code == 422
        assert rejected.json()["detail"]["reason"] == "recurrence_unsupported"


def _writable_synced_event(client):
    """Set up one confirmed, writable, non-recurring Google event entirely
    through the authenticated local API."""
    payload = connect_payload()
    payload["granted_scopes"] = [CALENDAR_LIST_SCOPE, EVENTS_WRITE_SCOPE]
    status = client.post(
        "/v1/calendar/accounts/connect", headers=HEADERS, json=payload
    ).json()
    calendar_id = status["calendars"][0]["id"]
    generation = str(uuid4())
    route = f"/v1/calendar/calendars/{calendar_id}/sync"
    client.post(
        f"{route}/begin",
        headers=HEADERS,
        json={"generation": generation, "mode": "full"},
    )
    client.post(
        f"{route}/page",
        headers=HEADERS,
        json={
            "generation": generation,
            "events": [
                {
                    "provider_event_id": "synthetic-seam-event",
                    "ical_uid": "synthetic-seam-event@example.invalid",
                    "provider_etag": '"synthetic-v1"',
                    "provider_updated_at": "2030-03-01T12:00:00Z",
                    "title": "Synthetic Seam Event",
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
    )
    client.post(
        f"{route}/complete",
        headers=HEADERS,
        json={"generation": generation, "next_sync_token": "synthetic-sync"},
    )
    return client.get("/v1/calendar/status", headers=HEADERS).json()["blocks"][0]


def test_conflict_resolution_round_trips_over_the_authenticated_local_api(tmp_path):
    """Cross-process seam: the whole conflict lifecycle over the real
    authenticated loopback routes against real SQLite, in the exact JSON shapes
    Rust deserializes. Unit suites on either side alone cannot prove this."""
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    with TestClient(create_production_app(settings, TOKEN)) as client:
        block = _writable_synced_event(client)
        assert block["provider_write_capability"]["eligible"] is True

        edited = client.post(
            "/v1/calendar/internal/write-intents/edit",
            headers=HEADERS,
            json={
                "command_id": str(uuid4()),
                "calendar_block_id": block["id"],
                "edit_kind": "edit",
                "expected_block_revision": block["revision"],
                "title": "Renamed through the seam",
                "locked_confirmed": True,
            },
        )
        assert edited.status_code == 200
        intent_id = edited.json()["intent"]["id"]

        # Ordinary ETag drift now rebases automatically, so a conflict is only
        # reachable once the whole bounded attempt budget is spent.
        state = "ready"
        for _ in range(MAX_AUTOMATIC_ATTEMPTS + 2):
            if state == "conflict":
                break
            if state != "attempting":
                assert (
                    client.post(
                        f"/v1/calendar/internal/write-intents/{intent_id}/attempt",
                        headers=HEADERS,
                        json={
                            "expected_state": state,
                            "executor_provenance": "direct_human",
                        },
                    ).status_code
                    == 200
                )
            conflicted = client.post(
                f"/v1/calendar/internal/write-intents/{intent_id}/result",
                headers=HEADERS,
                json={
                    "stage": "patch",
                    "result_class": "stale_precondition",
                    "safe_reason": "provider_values_changed",
                },
            )
            assert conflicted.status_code == 200
            state = conflicted.json()["state"]
        assert state == "conflict"

        # The renderer-facing projection reports the conflict truthfully,
        # including the safe failure classification.
        conflicted_block = client.get("/v1/calendar/status", headers=HEADERS).json()[
            "blocks"
        ][0]
        assert conflicted_block["provider_write_state"] == "conflict"
        assert conflicted_block["provider_write_failure_class"] == "stale_precondition"

        # Review differences returns only bounded, safe fields.
        review = client.post(
            "/v1/calendar/internal/write-intents/review-differences",
            headers=HEADERS,
            json={"calendar_block_id": block["id"]},
        )
        assert review.status_code == 200
        assert review.json()["desired_title"] == "Renamed through the seam"
        assert review.json()["confirmed_title"] == "Synthetic Seam Event"
        for forbidden in ("etag", "provider_event_id", "keychain", "token"):
            assert forbidden not in review.text

        # Apply my Ion changes rebases onto fresh authority and re-authorizes.
        applied = client.post(
            "/v1/calendar/internal/write-intents/apply-ion-changes",
            headers=HEADERS,
            json={
                "command_id": str(uuid4()),
                "calendar_block_id": block["id"],
                "expected_block_revision": conflicted_block["revision"],
            },
        )
        assert applied.status_code == 200
        assert applied.json()["intent"]["state"] == "ready"
        assert applied.json()["intent"]["id"] != intent_id
        assert "etag" not in applied.text

        # The rebased write is genuinely dispatchable through the same routes.
        ready = client.post(
            "/v1/calendar/internal/write-intents/ready", headers=HEADERS, json={}
        ).json()
        assert [plan["id"] for plan in ready] == [applied.json()["intent"]["id"]]
        assert ready[0]["expected_provider_etag"] == '"synthetic-v1"'

        # A resolution attempt with nothing left to resolve is a truthful,
        # allowlisted safe reason over the wire -- the exact contract the Rust
        # seam test asserts it can translate.
        blocked = client.post(
            "/v1/calendar/internal/write-intents/keep-google-version",
            headers=HEADERS,
            json={
                "command_id": str(uuid4()),
                "calendar_block_id": block["id"],
                "expected_block_revision": conflicted_block["revision"],
            },
        )
        assert blocked.status_code == 422
        assert blocked.json()["detail"]["reason"] == "no_conflict_to_resolve"


def test_series_split_lifecycle_over_the_authenticated_local_api(tmp_path):
    """Cross-process seam: a `this and following` split driven entirely through
    the real authenticated loopback routes against real SQLite, including the
    durable ordering that keeps the new master blocked until the trim is
    provider-confirmed."""
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    with TestClient(create_production_app(settings, TOKEN)) as client:
        payload = connect_payload()
        payload["granted_scopes"] = [CALENDAR_LIST_SCOPE, EVENTS_WRITE_SCOPE]
        status = client.post(
            "/v1/calendar/accounts/connect", headers=HEADERS, json=payload
        ).json()
        calendar_id = status["calendars"][0]["id"]
        generation = str(uuid4())
        route = f"/v1/calendar/calendars/{calendar_id}/sync"
        client.post(
            f"{route}/begin",
            headers=HEADERS,
            json={"generation": generation, "mode": "full"},
        )
        client.post(
            f"{route}/page",
            headers=HEADERS,
            json={
                "generation": generation,
                "events": [
                    {
                        "provider_event_id": "synthetic-split-series",
                        "provider_etag": '"series-v1"',
                        "title": "Synthetic Split Series",
                        "status": "confirmed",
                        "transparency": "opaque",
                        "recurrence": ["RRULE:FREQ=WEEKLY"],
                        "start": {
                            "date_time": "2030-03-04T09:00:00-08:00",
                            "timezone": "America/Los_Angeles",
                        },
                        "end": {
                            "date_time": "2030-03-04T10:00:00-08:00",
                            "timezone": "America/Los_Angeles",
                        },
                    }
                ],
            },
        )
        client.post(
            f"{route}/complete",
            headers=HEADERS,
            json={"generation": generation, "next_sync_token": "synthetic-sync"},
        )
        master = client.get("/v1/calendar/status", headers=HEADERS).json()["blocks"][0]

        split = client.post(
            "/v1/calendar/internal/write-intents/edit",
            headers=HEADERS,
            json={
                "command_id": str(uuid4()),
                "calendar_block_id": master["id"],
                "edit_kind": "edit",
                "expected_block_revision": master["revision"],
                "title": "Renamed from here forward",
                "recurrence_scope": "this_and_following",
                "occurrence_original_start": {
                    "date_time": "2030-03-18T09:00:00-08:00",
                    "timezone": "America/Los_Angeles",
                },
                "recurrence_risk_confirmed": True,
                "locked_confirmed": True,
            },
        )
        assert split.status_code == 200
        trim_id = split.json()["intent"]["id"]
        assert split.json()["intent"]["operation"] == "patch"

        # Two canonical masters now exist locally; the future one is pending.
        blocks = split.json()["status"]["blocks"]
        assert len(blocks) == 2
        future = next(item for item in blocks if item["id"] != master["id"])
        assert future["recurrence_kind"] == "master"
        assert future["provider_write_state"] == "pending"

        # Only the trim is dispatchable, and it carries the generated bounded
        # termination plus the confirmed non-wildcard ETag.
        ready = client.post(
            "/v1/calendar/internal/write-intents/ready", headers=HEADERS, json={}
        ).json()
        assert [plan["id"] for plan in ready] == [trim_id]
        assert ready[0]["desired_values"]["recurrence"] == [
            "RRULE:FREQ=WEEKLY;UNTIL=20300318T165959Z"
        ]
        assert ready[0]["expected_provider_etag"] == '"series-v1"'

        client.post(
            f"/v1/calendar/internal/write-intents/{trim_id}/attempt",
            headers=HEADERS,
            json={"expected_state": "ready", "executor_provenance": "direct_human"},
        )
        confirmed = client.post(
            f"/v1/calendar/internal/write-intents/{trim_id}/reconcile-patch",
            headers=HEADERS,
            json={
                "expected_state": "attempting",
                "resolution_kind": "patch_response",
                "event": {
                    "provider_event_id": "synthetic-split-series",
                    "provider_etag": '"series-v2"',
                    "title": "Synthetic Split Series",
                    "status": "confirmed",
                    "recurrence": ["RRULE:FREQ=WEEKLY;UNTIL=20300318T165959Z"],
                    "start": {
                        "date_time": "2030-03-04T09:00:00-08:00",
                        "timezone": "America/Los_Angeles",
                    },
                    "end": {
                        "date_time": "2030-03-04T10:00:00-08:00",
                        "timezone": "America/Los_Angeles",
                    },
                },
            },
        )
        assert confirmed.status_code == 200
        assert confirmed.json()["state"] == "completed"

        # Only now is the new future master released for dispatch, with its
        # deterministic identity and no inherited ETag.
        released = client.post(
            "/v1/calendar/internal/write-intents/ready", headers=HEADERS, json={}
        ).json()
        assert len(released) == 1
        assert released[0]["operation"] == "create"
        assert released[0]["calendar_block_id"] == future["id"]
        assert released[0]["expected_provider_etag"] is None
        assert released[0]["desired_values"]["recurrence"] == ["RRULE:FREQ=WEEKLY"]


def test_rust_safe_reason_allowlist_matches_python_route_allowlist():
    """The Rust `safe_calendar_write_reason` allowlist and Python's
    `SAFE_CALENDAR_WRITE_REASONS` are independently maintained (Rust cannot
    import Python). If a newly added safe reason lands in one without the
    other, that reason silently degrades to a generic message on whichever
    side was missed. Parse the Rust source directly so this drifts loudly."""
    rust_path = (
        Path(__file__).resolve().parents[3]
        / "apps"
        / "desktop"
        / "src-tauri"
        / "src"
        / "google_calendar.rs"
    )
    source = rust_path.read_text()
    match = re.search(
        r"fn safe_calendar_write_reason\(reason: &str\) -> bool \{"
        r"\s*matches!\(\s*reason,\s*(?P<arms>.*?)\)\s*\}",
        source,
        re.DOTALL,
    )
    assert match is not None, "safe_calendar_write_reason not found"
    rust_reasons = set(re.findall(r'"([a-z_]+)"', match.group("arms")))
    assert rust_reasons == SAFE_CALENDAR_WRITE_REASONS, (
        "Rust safe_calendar_write_reason and Python SAFE_CALENDAR_WRITE_REASONS "
        "have drifted apart -- update both allowlists together."
    )


def test_etag_drift_converges_automatically_over_the_authenticated_local_api(tmp_path):
    """Cross-layer automatic convergence: the exact call sequence the Rust
    dispatcher makes, over the real authenticated loopback API against real
    SQLite, with a synthetic provider standing in for Google.

    The recent real defects all escaped isolated suites, so this asserts the
    whole seam: an ordinary edit meets an ETag change, re-reads confirmed state,
    rebases onto it, retries, and settles -- with no conflict ever surfacing to
    the renderer and no human action anywhere in the sequence.
    """
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    with TestClient(create_production_app(settings, TOKEN)) as client:
        block = _writable_synced_event(client)

        edited = client.post(
            "/v1/calendar/internal/write-intents/edit",
            headers=HEADERS,
            json={
                "command_id": str(uuid4()),
                "calendar_block_id": block["id"],
                "edit_kind": "edit",
                "expected_block_revision": block["revision"],
                "title": "Renamed through the seam",
                "recurrence_scope": "single",
            },
        )
        assert edited.status_code == 200
        intent_id = edited.json()["intent"]["id"]

        # Google rejects the precondition: it moved while Ion was writing.
        assert (
            client.post(
                f"/v1/calendar/internal/write-intents/{intent_id}/attempt",
                headers=HEADERS,
                json={
                    "expected_state": "ready",
                    "executor_provenance": "direct_human",
                },
            ).status_code
            == 200
        )
        drifted = client.post(
            f"/v1/calendar/internal/write-intents/{intent_id}/result",
            headers=HEADERS,
            json={
                "stage": "patch",
                "result_class": "stale_precondition",
                "safe_reason": "provider_values_changed",
            },
        )
        assert drifted.status_code == 200
        assert drifted.json()["state"] == "ambiguous", (
            "ordinary drift must route to an automatic re-read, not a conflict"
        )

        # The renderer must see a change still in flight -- never review copy.
        drifting_block = client.get("/v1/calendar/status", headers=HEADERS).json()[
            "blocks"
        ][0]
        assert drifting_block["provider_write_state"] == "pending"
        assert drifting_block["provider_write_failure_class"] is None

        # Ion re-reads confirmed provider state. Google independently changed a
        # field Ion never touched.
        assert (
            client.post(
                f"/v1/calendar/internal/write-intents/{intent_id}/attempt",
                headers=HEADERS,
                json={
                    "expected_state": "ambiguous",
                    "executor_provenance": "recovery",
                },
            ).status_code
            == 200
        )
        rebased = client.post(
            f"/v1/calendar/internal/write-intents/{intent_id}/reconcile-patch",
            headers=HEADERS,
            json={
                "resolution_kind": "identity_lookup",
                "event": {
                    "provider_event_id": "synthetic-seam-event",
                    "provider_etag": '"synthetic-v2"',
                    "title": "Synthetic Seam Event",
                    "location": "Moved in Google",
                    "status": "confirmed",
                    "start": {
                        "date_time": "2030-03-10T09:00:00-07:00",
                        "timezone": "America/Los_Angeles",
                    },
                    "end": {
                        "date_time": "2030-03-10T10:00:00-07:00",
                        "timezone": "America/Los_Angeles",
                    },
                },
            },
        )
        assert rebased.status_code == 200
        assert rebased.json()["state"] == "ready", (
            "the pending intent must re-arm automatically against fresh state"
        )
        assert "etag" not in rebased.text

        # Google's own change landed; the user's pending change still shows.
        merged = client.get("/v1/calendar/status", headers=HEADERS).json()["blocks"][0]
        assert merged["location"] == "Moved in Google"
        assert merged["title"] == "Renamed through the seam"
        assert merged["provider_write_state"] == "pending"

        # The retry carries Google's fresh ETag, and settles.
        assert (
            client.post(
                f"/v1/calendar/internal/write-intents/{intent_id}/attempt",
                headers=HEADERS,
                json={
                    "expected_state": "ready",
                    "executor_provenance": "recovery",
                },
            ).status_code
            == 200
        )
        settled = client.post(
            f"/v1/calendar/internal/write-intents/{intent_id}/reconcile-patch",
            headers=HEADERS,
            json={
                "resolution_kind": "patch_response",
                "event": {
                    "provider_event_id": "synthetic-seam-event",
                    "provider_etag": '"synthetic-v3"',
                    "title": "Renamed through the seam",
                    "location": "Moved in Google",
                    "status": "confirmed",
                    "start": {
                        "date_time": "2030-03-10T09:00:00-07:00",
                        "timezone": "America/Los_Angeles",
                    },
                    "end": {
                        "date_time": "2030-03-10T10:00:00-07:00",
                        "timezone": "America/Los_Angeles",
                    },
                },
            },
        )
        assert settled.status_code == 200
        assert settled.json()["state"] == "completed"

        final = client.get("/v1/calendar/status", headers=HEADERS).json()["blocks"][0]
        assert final["provider_write_state"] == "synced"
        assert final["title"] == "Renamed through the seam"
        assert final["location"] == "Moved in Google", (
            "Google's independent change must survive Ion's write"
        )


def _writable_recurring_master(client):
    """One confirmed, writable, weekly Google master over the real API."""
    payload = connect_payload()
    payload["granted_scopes"] = [CALENDAR_LIST_SCOPE, EVENTS_WRITE_SCOPE]
    status = client.post(
        "/v1/calendar/accounts/connect", headers=HEADERS, json=payload
    ).json()
    account_id = status["accounts"][0]["id"]
    client.post(
        f"/v1/calendar/accounts/{account_id}/write-access",
        headers=HEADERS,
        json={"granted_scopes": [CALENDAR_LIST_SCOPE, EVENTS_WRITE_SCOPE]},
    )
    calendar_id = status["calendars"][0]["id"]
    generation = str(uuid4())
    route = f"/v1/calendar/calendars/{calendar_id}/sync"
    client.post(
        f"{route}/begin",
        headers=HEADERS,
        json={"generation": generation, "mode": "full"},
    )
    client.post(
        f"{route}/page",
        headers=HEADERS,
        json={
            "generation": generation,
            "events": [
                {
                    "provider_event_id": "synthetic-seam-master",
                    "ical_uid": "synthetic-seam-master@example.invalid",
                    "provider_etag": '"master-v1"',
                    "provider_updated_at": "2030-03-01T12:00:00Z",
                    "title": "Synthetic Seam Series",
                    "status": "confirmed",
                    "transparency": "opaque",
                    "recurrence": ["RRULE:FREQ=WEEKLY"],
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
    )
    client.post(
        f"{route}/complete",
        headers=HEADERS,
        json={"generation": generation, "next_sync_token": "synthetic-sync"},
    )
    return client.get("/v1/calendar/status", headers=HEADERS).json()["blocks"][0]


def test_occurrence_master_drift_converges_across_the_authenticated_local_api(tmp_path):
    """Cross-layer regression for the exact real-owner acceptance failure.

    This drives the same call sequence the Rust dispatcher makes for a
    `This event` write -- over the real authenticated loopback API, against real
    SQLite, with a synthetic provider standing in for Google -- and asserts the
    renderer-visible projection never becomes a review task.

    The previous defect was invisible to isolated tests: the master ETag lives
    inside the intent's recurrence identity, resolution treated a change to it
    as an identity failure, and that failure consumed no attempt, so the loop
    never terminated.
    """
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    with TestClient(create_production_app(settings, TOKEN)) as client:
        master = _writable_recurring_master(client)
        original_start = {
            "date": None,
            "date_time": "2030-03-17T09:00:00-07:00",
            "timezone": "America/Los_Angeles",
        }

        edited = client.post(
            "/v1/calendar/internal/write-intents/edit",
            headers=HEADERS,
            json={
                "command_id": str(uuid4()),
                "calendar_block_id": master["id"],
                "edit_kind": "edit",
                "expected_block_revision": master["revision"],
                "title": "Renamed one occurrence",
                "recurrence_scope": "occurrence",
                "occurrence_original_start": original_start,
            },
        )
        assert edited.status_code == 200
        intent_id = edited.json()["intent"]["id"]

        assert (
            client.post(
                f"/v1/calendar/internal/write-intents/{intent_id}/attempt",
                headers=HEADERS,
                json={
                    "expected_state": "ready",
                    "executor_provenance": "direct_human",
                },
            ).status_code
            == 200
        )

        # Google's master moved between queueing and dispatch. This is the
        # condition that used to loop forever.
        resolved = client.post(
            f"/v1/calendar/internal/write-intents/{intent_id}/resolve-occurrence",
            headers=HEADERS,
            json={
                "expected_state": "attempting",
                "master": {
                    "provider_event_id": "synthetic-seam-master",
                    "provider_etag": '"master-v2"',
                    "title": "Synthetic Seam Series",
                    "status": "confirmed",
                    "recurrence": ["RRULE:FREQ=WEEKLY"],
                    "start": {
                        "date_time": "2030-03-10T09:00:00-07:00",
                        "timezone": "America/Los_Angeles",
                    },
                    "end": {
                        "date_time": "2030-03-10T10:00:00-07:00",
                        "timezone": "America/Los_Angeles",
                    },
                },
                "instance": {
                    "provider_event_id": "synthetic-seam-instance",
                    "provider_etag": '"instance-v1"',
                    "title": "Synthetic Seam Series",
                    "status": "confirmed",
                    "recurring_event_id": "synthetic-seam-master",
                    "original_start": original_start,
                    "start": {
                        "date_time": "2030-03-17T09:00:00-07:00",
                        "timezone": "America/Los_Angeles",
                    },
                    "end": {
                        "date_time": "2030-03-17T10:00:00-07:00",
                        "timezone": "America/Los_Angeles",
                    },
                },
            },
        )
        assert resolved.status_code == 200
        assert resolved.json()["state"] == "attempting", (
            "master drift must be absorbed, not escalated"
        )
        # The dispatch plan now carries Google's fresh master authority, so the
        # retry cannot re-derive the stale identity that caused the loop. This
        # is an internal dispatch route, so it legitimately carries ETags.
        assert (
            resolved.json()["base_values"]["recurrence_identity"][
                "master_provider_etag"
            ]
            == '"master-v2"'
        )

        drifting = client.get("/v1/calendar/status", headers=HEADERS).json()["blocks"][
            0
        ]
        assert drifting["provider_write_state"] == "pending"
        assert drifting["provider_write_state"] != "conflict"
        assert drifting["provider_write_failure_class"] is None

        settled = client.post(
            f"/v1/calendar/internal/write-intents/{intent_id}/reconcile-patch",
            headers=HEADERS,
            json={
                "resolution_kind": "patch_response",
                "event": {
                    "provider_event_id": "synthetic-seam-instance",
                    "provider_etag": '"instance-v2"',
                    "title": "Renamed one occurrence",
                    "status": "confirmed",
                    "recurring_event_id": "synthetic-seam-master",
                    "original_start": original_start,
                    "start": {
                        "date_time": "2030-03-17T09:00:00-07:00",
                        "timezone": "America/Los_Angeles",
                    },
                    "end": {
                        "date_time": "2030-03-17T10:00:00-07:00",
                        "timezone": "America/Los_Angeles",
                    },
                },
            },
        )
        assert settled.status_code == 200
        assert settled.json()["state"] == "completed"

        blocks = client.get("/v1/calendar/status", headers=HEADERS).json()["blocks"]
        assert all(item["provider_write_state"] != "conflict" for item in blocks)
        exception = next(
            item for item in blocks if item["recurrence_kind"] == "exception"
        )
        assert exception["title"] == "Renamed one occurrence"


def test_successive_human_edits_are_accepted_across_the_authenticated_local_api(
    tmp_path,
):
    """Cross-layer regression for the accepted successive-edit contract.

    Drives the exact call sequence the Rust dispatcher makes -- over the real
    authenticated loopback API, against real SQLite, with a synthetic provider
    standing in for Google -- for the case the owner cares about: a first write
    is genuinely unsettled when the owner acts again.

    Provider dispatch stays serialized; the human never does.
    """
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    with TestClient(create_production_app(settings, TOKEN)) as client:
        block = _writable_synced_event(client)

        def edit(title):
            response = client.post(
                "/v1/calendar/internal/write-intents/edit",
                headers=HEADERS,
                json={
                    "command_id": str(uuid4()),
                    "calendar_block_id": block["id"],
                    "edit_kind": "edit",
                    "expected_block_revision": block["revision"],
                    "title": title,
                    "recurrence_scope": "single",
                },
            )
            assert response.status_code == 200, response.text
            return response.json()["intent"]

        # Two rapid edits with nothing in flight: the obsolete one is retired
        # rather than costing a provider round-trip.
        first = edit("Dragged to 3 PM")
        second = edit("Dragged to 4 PM")
        assert second["state"] == "ready"
        ready = client.post(
            "/v1/calendar/internal/write-intents/ready", headers=HEADERS, json={}
        ).json()
        assert [plan["id"] for plan in ready] == [second["id"]]
        assert first["id"] != second["id"]

        # Now put that write genuinely in flight and edit again.
        assert (
            client.post(
                f"/v1/calendar/internal/write-intents/{second['id']}/attempt",
                headers=HEADERS,
                json={
                    "expected_state": "ready",
                    "executor_provenance": "direct_human",
                },
            ).status_code
            == 200
        )
        third = edit("Dragged to 5 PM")
        assert third["state"] == "queued", "accepted durably, never refused"

        # No parallel provider write may target the same event...
        assert (
            client.post(
                "/v1/calendar/internal/write-intents/ready", headers=HEADERS, json={}
            ).json()
            == []
        )
        # ...and the owner already sees their newest value.
        mid = client.get("/v1/calendar/status", headers=HEADERS).json()["blocks"][0]
        assert mid["provider_write_overlay"]["title"] == "Dragged to 5 PM"
        assert mid["provider_write_state"] == "pending"

        # The in-flight write settles; the newest intent is released and
        # re-aimed at the authority that write confirmed.
        settled = client.post(
            f"/v1/calendar/internal/write-intents/{second['id']}/reconcile-patch",
            headers=HEADERS,
            json={
                "resolution_kind": "patch_response",
                "event": {
                    "provider_event_id": "synthetic-seam-event",
                    "provider_etag": '"seam-v2"',
                    "title": "Dragged to 4 PM",
                    "status": "confirmed",
                    "start": {
                        "date_time": "2030-03-10T09:00:00-07:00",
                        "timezone": "America/Los_Angeles",
                    },
                    "end": {
                        "date_time": "2030-03-10T10:00:00-07:00",
                        "timezone": "America/Los_Angeles",
                    },
                },
            },
        )
        assert settled.status_code == 200
        assert settled.json()["state"] == "completed"

        released = client.post(
            "/v1/calendar/internal/write-intents/ready", headers=HEADERS, json={}
        ).json()
        assert [plan["id"] for plan in released] == [third["id"]]
        assert released[0]["expected_provider_etag"] == '"seam-v2"'

        # The confirmed value passing through an obsolete state never becomes
        # what the owner sees, and none of this is a review task.
        between = client.get("/v1/calendar/status", headers=HEADERS).json()["blocks"][0]
        assert between["title"] == "Dragged to 5 PM"
        assert between["provider_write_state"] == "pending"

        assert (
            client.post(
                f"/v1/calendar/internal/write-intents/{third['id']}/attempt",
                headers=HEADERS,
                json={"expected_state": "ready", "executor_provenance": "recovery"},
            ).status_code
            == 200
        )
        final = client.post(
            f"/v1/calendar/internal/write-intents/{third['id']}/reconcile-patch",
            headers=HEADERS,
            json={
                "resolution_kind": "patch_response",
                "event": {
                    "provider_event_id": "synthetic-seam-event",
                    "provider_etag": '"seam-v3"',
                    "title": "Dragged to 5 PM",
                    "status": "confirmed",
                    "start": {
                        "date_time": "2030-03-10T09:00:00-07:00",
                        "timezone": "America/Los_Angeles",
                    },
                    "end": {
                        "date_time": "2030-03-10T10:00:00-07:00",
                        "timezone": "America/Los_Angeles",
                    },
                },
            },
        )
        assert final.status_code == 200
        assert final.json()["state"] == "completed"

        end = client.get("/v1/calendar/status", headers=HEADERS).json()["blocks"][0]
        assert end["title"] == "Dragged to 5 PM"
        assert end["provider_write_state"] == "synced"
