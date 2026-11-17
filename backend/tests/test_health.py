from datetime import UTC, datetime

from fastapi.testclient import TestClient

from app.main import create_app
from app.services.health_service import HealthService
from app.settings import Settings


def _settings() -> Settings:
    # Explicit values so tests never depend on a real .env file.
    return Settings(_env_file=None, app_env="test")


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(create_app(_settings()))

    response = client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["environment"] == "test"


def test_health_service_uses_injected_clock() -> None:
    fixed = datetime(2026, 11, 20, 12, 0, tzinfo=UTC)

    result = HealthService(_settings(), clock=lambda: fixed).status()

    assert result.checked_at == fixed


def test_cors_allows_only_configured_origin() -> None:
    client = TestClient(create_app(_settings()))

    allowed = client.get("/api/health", headers={"Origin": "http://localhost:5173"})
    blocked = client.get("/api/health", headers={"Origin": "https://evil.example"})

    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in blocked.headers
