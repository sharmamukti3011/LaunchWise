"""Interactive docs and the OpenAPI schema are for development only."""

from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings

DOC_PATHS = ["/docs", "/redoc", "/openapi.json", "/docs/oauth2-redirect"]


def client(env: str) -> TestClient:
    return TestClient(create_app(Settings(_env_file=None, app_env=env)))


@pytest.mark.parametrize("env", ["production", "test"])
@pytest.mark.parametrize("path", DOC_PATHS)
def test_docs_and_schema_are_not_served_outside_development(env: str, path: str) -> None:
    assert client(env).get(path).status_code == 404


@pytest.mark.parametrize("env", ["production", "test"])
def test_the_app_does_not_even_register_the_doc_routes_outside_development(env: str) -> None:
    app = create_app(Settings(_env_file=None, app_env=env))
    assert app.docs_url is None and app.redoc_url is None and app.openapi_url is None


def test_docs_and_schema_are_served_in_development() -> None:
    dev = client("development")
    for path in ("/docs", "/redoc", "/openapi.json"):
        assert dev.get(path).status_code == 200, path
    schema: Any = dev.get("/openapi.json").json()
    assert "/api/analyze" in schema["paths"]


def test_the_real_api_still_works_when_docs_are_off() -> None:
    prod = client("production")
    assert prod.get("/api/health").status_code == 200
    assert prod.post("/api/analyze", json={}).status_code == 422  # reaches validation, not a 404


def test_the_schema_can_still_be_generated_in_process_for_tests_and_tooling() -> None:
    app = create_app(Settings(_env_file=None, app_env="production"))
    assert sorted(app.openapi()["paths"]) == [
        "/api/analyze",
        "/api/analyze/explain",
        "/api/contact",
        "/api/demo/explain/{scenario_id}",
        "/api/demo/run/{scenario_id}",
        "/api/demo/scenarios",
        "/api/health",
        "/api/market-evidence",
    ]
