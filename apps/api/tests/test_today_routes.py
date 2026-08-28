from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from ion_api.main import SESSION_HEADER, create_production_app
from ion_api.migrations import upgrade_to_head
from ion_api.settings import Settings


def test_today_routes_are_authenticated_typed_and_revision_safe(tmp_path):
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    token = "a" * 43
    timezone = "America/Los_Angeles"
    planning_date = datetime.now(ZoneInfo(timezone)).date().isoformat()
    headers = {SESSION_HEADER: token}
    with TestClient(create_production_app(settings, token)) as client:
        assert (
            client.get(
                "/v1/today",
                params={"planning_date": planning_date, "timezone": timezone},
            ).status_code
            == 401
        )
        task = client.post(
            "/v1/tasks", headers=headers, json={"title": "Synthetic Today Task"}
        ).json()
        created = client.post(
            "/v1/today/plans",
            headers=headers,
            json={
                "planning_date": planning_date,
                "timezone": timezone,
                "task_id": task["id"],
                "role": "priority",
            },
        )
        assert created.status_code == 201
        plan = created.json()["plan"]["priorities"][0]["plan"]
        stale = client.put(
            f"/v1/today/plans/{plan['id']}/role",
            headers=headers,
            json={
                "planning_date": planning_date,
                "timezone": timezone,
                "expected_revision": plan["revision"] + 1,
                "role": "backup",
            },
        )
        invalid_day = client.get(
            "/v1/today",
            headers=headers,
            params={"planning_date": "2000-01-01", "timezone": timezone},
        )
    assert stale.status_code == 409
    assert stale.json()["detail"]["code"] == "revision_conflict"
    assert invalid_day.status_code == 422
    assert invalid_day.json()["detail"]["code"] == "validation"
