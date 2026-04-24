from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health_returns_200() -> None:
    response = client.get("/health")
    assert response.status_code == 200


def test_health_schema() -> None:
    response = client.get("/health")
    body = response.json()
    assert "status" in body
    assert "version" in body
    assert "vault_accessible" in body
    assert "ollama_accessible" in body
    assert "jobs_db_accessible" in body
    assert "uptime_seconds" in body
    assert isinstance(body["uptime_seconds"], int)


def test_health_status_values() -> None:
    response = client.get("/health")
    body = response.json()
    assert body["status"] in ("healthy", "degraded")
    assert body["version"] == "0.1.0"


def test_health_no_auth_required() -> None:
    response = client.get("/health", headers={})
    assert response.status_code == 200
