"""Phase 2C-R0 cross-layer seam tests.

Phase 2C v1 repeatedly passed isolated tests while production seams were broken.
`this and following` was implemented end to end in the Python domain, with
passing tests, while the Tauri command's scope allowlist still read
`single | occurrence | series`; every real attempt failed as
`local_state_invalid`. Green domain tests, broken product.

So these tests do not call the coordinator. They drive the **authenticated
production app** over a real SQLite database at migration head 0007, using the
exact request bodies the Rust layer serializes, and assert the properties that
isolated tests could not see.

No Google request is made, and R0 has no code path that could make one.
"""

import json
import sqlite3
from pathlib import Path

from calendar_write_fixtures import BLOCK_ID, intent_payload, seed_writable_event
from fastapi.testclient import TestClient

from ion_api.db import create_database_engine
from ion_api.main import create_production_app
from ion_api.migrations import upgrade_to_head
from ion_api.settings import Settings

TOKEN = "synthetic-session-token"
HEADERS = {"X-Ion-Session": TOKEN}
INTENT_ROUTE = f"/v1/calendar/writes/blocks/{BLOCK_ID}/intent"

REPO_ROOT = Path(__file__).resolve().parents[3]
MANIFEST = json.loads(
    (REPO_ROOT / "contracts" / "calendar-write-vocabulary.json").read_text()
)
RUST_SOURCE = (
    REPO_ROOT / "apps" / "desktop" / "src-tauri" / "src" / "calendar_write.rs"
).read_text()
TS_SOURCE = (
    REPO_ROOT / "apps" / "desktop" / "src" / "calendarWriteContract.ts"
).read_text()


def stack(tmp_path, **seed):
    """The real seam: authenticated production app over real SQLite at 0007."""

    tmp_path.mkdir(parents=True, exist_ok=True)
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    seed_writable_event(create_database_engine(settings.database_path), **seed)
    return settings, TestClient(create_production_app(settings, TOKEN))


def rows(settings, table):
    with sqlite3.connect(settings.database_path) as connection:
        connection.row_factory = sqlite3.Row
        return [dict(row) for row in connection.execute(f"SELECT * FROM {table}")]


def test_a_direct_human_intent_crosses_every_layer_and_is_durable(tmp_path):
    settings, client = stack(tmp_path)
    with client:
        assert client.post(INTENT_ROUTE, json=intent_payload()).status_code == 401

        response = client.post(INTENT_ROUTE, headers=HEADERS, json=intent_payload())
        assert response.status_code == 200
        receipt = response.json()
        assert receipt["accepted"] is True
        assert receipt["state"] == "ready"

        # Durable in SQLite before any provider execution, with no attempt made.
        stored = rows(settings, "calendar_provider_write_intents")
        assert len(stored) == 1
        assert stored[0]["provenance"] == "direct_human"
        assert stored[0]["attempt_count"] == 0
        assert stored[0]["last_attempt_at"] is None
        assert stored[0]["state"] == "ready"

        # And the audit trail exists in the same transaction.
        audit = rows(settings, "calendar_provider_write_audit")
        assert [entry["action"] for entry in audit] == ["write_intent_ready"]


def test_no_layer_adds_a_second_authorization_step(tmp_path):
    """A direct human action is the authorization; nothing may ask again."""

    settings, client = stack(tmp_path)
    with client:
        response = client.post(INTENT_ROUTE, headers=HEADERS, json=intent_payload())
        assert response.status_code == 200
        body = response.text
        # The receipt is an acknowledgement, not a request for confirmation.
        assert response.json()["accepted"] is True
        for forbidden in (
            "needs_review",
            "requires_approval",
            "awaiting_confirmation",
            "confirm",
            "review",
            "apply_ion",
            "keep_google",
            "write_pending",
        ):
            assert forbidden not in body

    # An approval-shaped field is rejected outright rather than ignored.
    settings, client = stack(tmp_path / "second")
    with client:
        refused = client.post(
            INTENT_ROUTE,
            headers=HEADERS,
            json=intent_payload(approved=True),
        )
        assert refused.status_code == 422


def test_the_renderer_cannot_inject_provider_authority(tmp_path):
    """Every provider-authority field is refused by the contract, not ignored."""

    for field, value in (
        ("provider_event_id", "attacker-event"),
        ("expected_provider_etag", '"attacker-etag"'),
        ("calendar_id", "cccccccc-cccc-4ccc-8ccc-cccccccccccc"),
        ("account_id", "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"),
        ("method", "PUT"),
        ("url", "https://www.googleapis.com/calendar/v3/calendars/x/events/y"),
        ("headers", {"If-Match": "*"}),
        ("provenance", "ai"),
    ):
        settings, client = stack(tmp_path / field)
        with client:
            response = client.post(
                INTENT_ROUTE, headers=HEADERS, json=intent_payload(**{field: value})
            )
        assert response.status_code == 422, field
        assert rows(settings, "calendar_provider_write_intents") == []

    # The ETag actually used is the confirmed one the server derived.
    settings, client = stack(tmp_path / "derived")
    with client:
        client.post(INTENT_ROUTE, headers=HEADERS, json=intent_payload())
    stored = rows(settings, "calendar_provider_write_intents")[0]
    assert stored["expected_provider_etag"] == '"synthetic-etag-1"'


def test_the_closed_changed_field_allowlist_survives_end_to_end(tmp_path):
    for payload in (
        intent_payload(changed_fields=["recurrence"], draft={"recurrence": "DAILY"}),
        intent_payload(changed_fields=["attendees"], draft={"attendees": []}),
        intent_payload(changed_fields=["title"], draft={"title": "x", "location": "y"}),
        intent_payload(changed_fields=[], draft={}),
        intent_payload(
            changed_fields=["title"], draft={"start": {"date": "2030-01-07"}}
        ),
    ):
        key = str(abs(hash(json.dumps(payload, sort_keys=True))))
        settings, client = stack(tmp_path / key)
        with client:
            response = client.post(INTENT_ROUTE, headers=HEADERS, json=payload)
        assert response.status_code == 422, payload
        assert rows(settings, "calendar_provider_write_intents") == []


def test_unknown_operation_or_scope_is_rejected_consistently(tmp_path):
    """The exact seam that broke Phase 2C v1 in production."""

    for payload in (
        intent_payload(operation="create"),
        intent_payload(operation="delete_event"),
        intent_payload(operation="delete_series"),
        intent_payload(recurrence_scope="occurrence"),
        intent_payload(recurrence_scope="series"),
        # The value whose absence from the Tauri allowlist produced
        # `local_state_invalid` on every real attempt in Phase 2C v1.
        intent_payload(recurrence_scope="this_and_following"),
    ):
        key = f"{payload['operation']}-{payload['recurrence_scope']}"
        settings, client = stack(tmp_path / key)
        with client:
            response = client.post(INTENT_ROUTE, headers=HEADERS, json=payload)
        assert response.status_code == 422, payload
        assert rows(settings, "calendar_provider_write_intents") == []


def test_provider_busy_never_refuses_a_human_action_across_the_seam(tmp_path):
    settings, client = stack(tmp_path)
    with client:
        first = client.post(INTENT_ROUTE, headers=HEADERS, json=intent_payload()).json()
        assert (
            client.post(
                "/v1/calendar/writes/internal/attempt",
                headers=HEADERS,
                json={"intent_id": first["intent_id"]},
            ).status_code
            == 200
        )

        # Provider work is in flight. The owner edits again, twice.
        for command in (
            "22222222-2222-4222-8222-222222222222",
            "33333333-3333-4333-8333-333333333333",
        ):
            again = client.post(
                INTENT_ROUTE,
                headers=HEADERS,
                json=intent_payload(command_id=command),
            )
            assert again.status_code == 200
            assert again.json()["accepted"] is True

        work = client.post("/v1/calendar/writes/internal/work", headers=HEADERS).json()
        # Serialized for the provider, never a refusal for the person.
        assert work["plans"] == []
        assert work["provider_busy"] is True

    assert len(rows(settings, "calendar_provider_write_intents")) == 3


def test_recovery_classification_survives_end_to_end(tmp_path):
    settings, client = stack(tmp_path)
    with client:
        receipt = client.post(
            INTENT_ROUTE, headers=HEADERS, json=intent_payload()
        ).json()
        client.post(
            "/v1/calendar/writes/internal/attempt",
            headers=HEADERS,
            json={"intent_id": receipt["intent_id"]},
        )
        outcome = client.post(
            "/v1/calendar/writes/internal/outcome",
            headers=HEADERS,
            json={
                "intent_id": receipt["intent_id"],
                "failure_class": "stale_precondition",
            },
        )
        assert outcome.json()["recovery"] == "provider_version_drift"

        recovered = client.post(
            "/v1/calendar/writes/internal/recover", headers=HEADERS
        ).json()
        entry = recovered["entries"][0]
        assert entry["recovery"] == "provider_version_drift"
        assert entry["automatic"] is True
        assert entry["owner_action"] is False

    # Ordinary drift never becomes a stored conflict.
    assert all(
        row["state"] != "conflict"
        for row in rows(settings, "calendar_provider_write_intents")
    )


def test_an_unknown_failure_class_is_refused_rather_than_generically_classified(
    tmp_path,
):
    settings, client = stack(tmp_path)
    with client:
        receipt = client.post(
            INTENT_ROUTE, headers=HEADERS, json=intent_payload()
        ).json()
        client.post(
            "/v1/calendar/writes/internal/attempt",
            headers=HEADERS,
            json={"intent_id": receipt["intent_id"]},
        )
        response = client.post(
            "/v1/calendar/writes/internal/outcome",
            headers=HEADERS,
            json={"intent_id": receipt["intent_id"], "failure_class": "something_new"},
        )
    assert response.status_code == 422


def test_a_restart_repairs_in_flight_work_across_the_seam(tmp_path):
    settings, client = stack(tmp_path)
    with client:
        receipt = client.post(
            INTENT_ROUTE, headers=HEADERS, json=intent_payload()
        ).json()
        client.post(
            "/v1/calendar/writes/internal/attempt",
            headers=HEADERS,
            json={"intent_id": receipt["intent_id"]},
        )

    # A new process against the same durable database.
    with TestClient(create_production_app(settings, TOKEN)) as restarted:
        recovered = restarted.post(
            "/v1/calendar/writes/internal/recover", headers=HEADERS
        ).json()
        assert recovered["repaired_in_flight"] == 1
        assert recovered["entries"][0]["state"] == "ambiguous"
        work = restarted.post(
            "/v1/calendar/writes/internal/work", headers=HEADERS
        ).json()
        assert work["plans"] == []


def test_the_renderer_lane_never_reports_provider_lifecycle_state(tmp_path):
    """No renderer-facing response can produce "Not saved yet" on an event."""

    settings, client = stack(tmp_path)
    with client:
        receipt = client.post(INTENT_ROUTE, headers=HEADERS, json=intent_payload())
        status = client.get("/v1/calendar/status", headers=HEADERS)
    for body in (receipt.text, status.text):
        for forbidden in (
            "provider_write_state",
            "write_pending",
            "not_saved",
            "Not saved yet",
            "needs_review",
            "syncing",
        ):
            assert forbidden not in body


def test_r0_exposes_no_google_write_capability(tmp_path):
    settings, client = stack(tmp_path)
    with client:
        client.post(INTENT_ROUTE, headers=HEADERS, json=intent_payload())
        work = client.post("/v1/calendar/writes/internal/work", headers=HEADERS).json()
    assert len(work["plans"]) == 1
    assert work["plans"][0]["dispatchable"] is False
    assert MANIFEST["coordinator"]["dispatchable_operations"] == []
    # The R0 Rust write module reaches no Google endpoint or method. It talks
    # only to the authenticated loopback API through `product_request`.
    for forbidden in ("googleapis.com", "events.insert", "events.patch"):
        assert forbidden not in RUST_SOURCE
    assert "product_request(" in RUST_SOURCE


def test_tauri_and_python_vocabulary_cannot_silently_drift_apart():
    """Assert the *other* layers' source against the canonical manifest.

    Rust and TypeScript each have their own parity test. This one exists so that
    a change made only in Python still fails a Python test, which is the failure
    mode that let Phase 2C v1 ship a broken seam.
    """

    for value in MANIFEST["coordinator"]["accepted_operations"]:
        assert f'"{value}"' in RUST_SOURCE and f'"{value}"' in TS_SOURCE
    for value in MANIFEST["coordinator"]["accepted_recurrence_scopes"]:
        assert f'"{value}"' in RUST_SOURCE and f'"{value}"' in TS_SOURCE
    for value in MANIFEST["coordinator"]["changed_fields"]:
        assert f'"{value}"' in RUST_SOURCE and f'"{value}"' in TS_SOURCE
    recovery_kinds = (
        MANIFEST["recovery"]["automatic"] + MANIFEST["recovery"]["owner_action"]
    )
    for value in recovery_kinds:
        assert f'"{value}"' in RUST_SOURCE, value
        assert f'"{value}"' in TS_SOURCE, value
    # And the withdrawn vocabulary appears in no layer's allowlist.
    for forbidden in MANIFEST["recovery"]["forbidden"]:
        assert f'"{forbidden}",' not in TS_SOURCE
