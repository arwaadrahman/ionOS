from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi.testclient import TestClient

from ion_api.main import SESSION_HEADER, create_production_app
from ion_api.migrations import upgrade_to_head
from ion_api.settings import Settings


def test_home_route_is_authenticated_and_typed(tmp_path):
    settings = Settings(data_dir=tmp_path)
    upgrade_to_head(settings.database_path)
    token = "a" * 43
    timezone = "America/Los_Angeles"
    planning_date = datetime.now(ZoneInfo(timezone)).date().isoformat()
    params = {"planning_date": planning_date, "timezone": timezone}
    with TestClient(create_production_app(settings, token)) as client:
        assert client.get("/v1/home", params=params).status_code == 401
        response = client.get(
            "/v1/home", params=params, headers={SESSION_HEADER: token}
        )
        invalid = client.get(
            "/v1/home",
            params={"planning_date": "2000-01-01", "timezone": timezone},
            headers={SESSION_HEADER: token},
        )
    assert response.status_code == 200
    assert response.json()["core"] == {"nodes": [], "edges": []}
    assert invalid.status_code == 422
    assert invalid.json()["detail"]["code"] == "validation"
