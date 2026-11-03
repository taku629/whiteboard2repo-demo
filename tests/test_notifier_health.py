from fastapi.testclient import TestClient

from services.notifier.app import app


def test_health():
    r = TestClient(app).get("/health")
    assert r.status_code == 200
    assert r.json()["service"] == "notifier"
