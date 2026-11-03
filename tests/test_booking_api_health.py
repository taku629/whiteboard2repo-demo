from fastapi.testclient import TestClient

from services.booking_api.app import app


def test_health():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "booking_api"
