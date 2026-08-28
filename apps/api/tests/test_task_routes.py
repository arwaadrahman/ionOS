from fastapi.testclient import TestClient
from sqlalchemy import select

from ion_api.db import create_database_engine
from ion_api.main import SESSION_HEADER, create_production_app
from ion_api.migrations import upgrade_to_head
from ion_api.schema import audit_events
from ion_api.settings import Settings


def test_task_routes_require_production_auth_and_map_conflicts(tmp_path):
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    with TestClient(create_production_app(settings, "a" * 43)) as client:
        assert client.get("/v1/tasks").status_code == 401
        created = client.post(
            "/v1/tasks",
            headers={SESSION_HEADER: "a" * 43},
            json={"title": "Synthetic route task"},
        )
        assert created.status_code == 201
        task = created.json()
        edited = client.patch(
            f"/v1/tasks/{task['id']}",
            headers={SESSION_HEADER: "a" * 43},
            json={
                "expected_revision": task["revision"],
                "title": "Edited synthetic route task",
                "details": None,
                "importance": None,
                "estimated_minutes": None,
                "progress_percent": None,
                "deadline": {"kind": "none"},
                "project_id": None,
                "goal_id": None,
                "completion_evidence": None,
            },
        )
        assert edited.status_code == 200
        edited_task = edited.json()
        assert edited_task["title"] == "Edited synthetic route task"
        assert edited_task["revision"] == task["revision"] + 1
        completed = client.post(
            f"/v1/tasks/{task['id']}/complete",
            headers={SESSION_HEADER: "a" * 43},
            json={"expected_revision": edited_task["revision"]},
        )
        assert completed.status_code == 200
        stale = client.post(
            f"/v1/tasks/{task['id']}/trash",
            headers={SESSION_HEADER: "a" * 43},
            json={"expected_revision": task["revision"]},
        )

    assert stale.status_code == 409
    engine = create_database_engine(settings.database_path)
    with engine.connect() as connection:
        actions = connection.execute(
            select(audit_events.c.action).order_by(audit_events.c.occurred_at)
        ).scalars()
        assert list(actions) == ["created", "edited", "completed"]
    engine.dispose()
