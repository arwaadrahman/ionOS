from fastapi.testclient import TestClient

from ion_api.main import create_app
from ion_api.settings import Settings


def test_health_endpoint_is_available_from_an_explicit_development_origin(tmp_path):
    settings = Settings(data_dir=tmp_path)
    with TestClient(create_app(settings)) as client:
        response = client.get("/health", headers={"Origin": "http://127.0.0.1:1420"})

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
    assert response.headers["access-control-allow-origin"] == "http://127.0.0.1:1420"


def test_health_endpoint_does_not_grant_an_unlisted_origin(tmp_path):
    with TestClient(create_app(Settings(data_dir=tmp_path))) as client:
        response = client.get("/health", headers={"Origin": "https://example.test"})

    assert "access-control-allow-origin" not in response.headers
