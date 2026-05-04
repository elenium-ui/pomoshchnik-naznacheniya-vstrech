from fastapi.testclient import TestClient

from app.web.api.app import app


def test_health_route_returns_ok_payload():
    client = TestClient(app)

    response = client.get("/health")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["service"] == "miniapp-api"
    assert "timestamp_utc" in payload


def test_smoke_route_returns_ready_message():
    client = TestClient(app)

    response = client.get("/api/miniapp/smoke")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "ok"
    assert payload["message"] == "Mini App API shell is ready."

