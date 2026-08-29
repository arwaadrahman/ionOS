from fastapi.testclient import TestClient

from ion_api.main import SESSION_HEADER, create_production_app
from ion_api.migrations import upgrade_to_head
from ion_api.settings import Settings

TOKEN = "a" * 43
HEADERS = {SESSION_HEADER: TOKEN}


def test_organizer_routes_are_authenticated_and_return_safe_product_errors(tmp_path):
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)

    with TestClient(create_production_app(settings, TOKEN)) as client:
        assert client.get("/v1/areas").status_code == 401
        area_response = client.post(
            "/v1/areas", headers=HEADERS, json={"name": "Synthetic Area"}
        )
        assert area_response.status_code == 201
        area = area_response.json()
        goal_response = client.post(
            "/v1/goals",
            headers=HEADERS,
            json={
                "title": "Synthetic Goal",
                "kind": "outcome",
                "area_id": area["id"],
            },
        )
        assert goal_response.status_code == 201

        blocked = client.post(
            f"/v1/areas/{area['id']}/trash",
            headers=HEADERS,
            json={"expected_revision": area["revision"]},
        )
        assert blocked.status_code == 409
        assert blocked.json() == {
            "detail": {
                "code": "trash_blocked",
                "blockers": [{"entity": "goal", "count": 1}],
            }
        }

        archived = client.post(
            f"/v1/areas/{area['id']}/archive",
            headers=HEADERS,
            json={"expected_revision": area["revision"]},
        ).json()
        unavailable = client.post(
            "/v1/goals",
            headers=HEADERS,
            json={
                "title": "Rejected Goal",
                "kind": "outcome",
                "area_id": area["id"],
            },
        )
        assert unavailable.status_code == 409
        assert unavailable.json()["detail"] == {
            "code": "assignment_unavailable",
            "blockers": [],
        }

        stale = client.post(
            f"/v1/areas/{area['id']}/unarchive",
            headers=HEADERS,
            json={"expected_revision": area["revision"]},
        )
        assert stale.status_code == 409
        assert stale.json()["detail"]["code"] == "revision_conflict"
        assert archived["archived_at"] is not None

        invalid = client.post("/v1/projects", headers=HEADERS, json={"title": ""})
        assert invalid.status_code == 422
        assert invalid.json()["detail"] == {
            "code": "validation",
            "blockers": [],
        }

        assert client.get("/v1/recovery").status_code == 401
        recovery = client.get("/v1/recovery", headers=HEADERS)
        assert recovery.status_code == 200
        payload = recovery.json()
        assert payload["trash"] == []
        assert {
            (event["entity_type"], event["label"], event["authority"])
            for event in payload["recent_activity"]
        } == {
            ("area", "Synthetic Area", "direct"),
            ("goal", "Synthetic Goal", "direct"),
        }


def test_task_relationship_route_uses_the_complete_desired_pair(tmp_path):
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)

    with TestClient(create_production_app(settings, TOKEN)) as client:
        goal = client.post(
            "/v1/goals",
            headers=HEADERS,
            json={"title": "Relationship Goal", "kind": "outcome"},
        ).json()
        project = client.post(
            "/v1/projects",
            headers=HEADERS,
            json={"title": "Relationship Project"},
        ).json()
        task = client.post(
            "/v1/tasks", headers=HEADERS, json={"title": "Relationship Task"}
        ).json()

        linked = client.put(
            f"/v1/tasks/{task['id']}/relationships",
            headers=HEADERS,
            json={
                "expected_revision": task["revision"],
                "goal_id": goal["id"],
                "project_id": project["id"],
            },
        )
        assert linked.status_code == 200
        assert linked.json()["goal_id"] == goal["id"]
        assert linked.json()["project_id"] == project["id"]

        ordinary_edit = client.patch(
            f"/v1/tasks/{task['id']}",
            headers=HEADERS,
            json={
                "expected_revision": linked.json()["revision"],
                "title": "Edited Relationship Task",
                "goal_id": None,
                "project_id": None,
            },
        )
        assert ordinary_edit.status_code == 200
        assert ordinary_edit.json()["goal_id"] == goal["id"]
        assert ordinary_edit.json()["project_id"] == project["id"]

        cleared_goal_only = client.put(
            f"/v1/tasks/{task['id']}/relationships",
            headers=HEADERS,
            json={
                "expected_revision": ordinary_edit.json()["revision"],
                "goal_id": None,
                "project_id": project["id"],
            },
        )
        assert cleared_goal_only.status_code == 200
        assert cleared_goal_only.json()["goal_id"] is None
        assert cleared_goal_only.json()["project_id"] == project["id"]


def test_goal_lifecycle_can_persist_before_a_null_kind_patch_is_rejected(tmp_path):
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)

    with TestClient(create_production_app(settings, TOKEN)) as client:
        goal = client.post(
            "/v1/goals",
            headers=HEADERS,
            json={"title": "Original Goal", "kind": "outcome"},
        ).json()
        lifecycle = client.put(
            f"/v1/goals/{goal['id']}/state",
            headers=HEADERS,
            json={"expected_revision": goal["revision"], "state": "paused"},
        )
        assert lifecycle.status_code == 200

        invalid_patch = client.patch(
            f"/v1/goals/{goal['id']}",
            headers=HEADERS,
            json={
                "expected_revision": lifecycle.json()["revision"],
                "title": "Edited Goal",
                "description": None,
                "kind": None,
            },
        )
        assert invalid_patch.status_code == 422
        assert invalid_patch.json()["detail"]["code"] == "validation"

        persisted = client.get(f"/v1/goals/{goal['id']}", headers=HEADERS).json()[
            "goal"
        ]
        assert persisted["state"] == "paused"
        assert persisted["title"] == "Original Goal"
        assert persisted["revision"] == lifecycle.json()["revision"]
