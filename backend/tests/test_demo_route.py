"""GET /api/demo/scenarios and POST /api/demo/run/{id}, through the same gateway."""

import logging
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from tests.fakes import FakeClock

LIST_URL = "/api/demo/scenarios"
RUN = "/api/demo/run/"
IDS = ["pune-pivot", "pune-keep-original", "pune-nothing-viable", "noida-feasibility-only"]


def make_client(clock: FakeClock | None = None, **overrides: Any) -> TestClient:
    settings = Settings(_env_file=None, app_env="test", **overrides)
    return TestClient(create_app(settings, clock=clock), client=("203.0.113.7", 50000))


@pytest.fixture
def client() -> TestClient:
    return make_client()


def test_the_list_returns_the_four_scenarios_labelled_simulated(client: TestClient) -> None:
    response = client.get(LIST_URL)
    assert response.status_code == 200
    body = response.json()
    assert [s["id"] for s in body["scenarios"]] == IDS
    for scenario in body["scenarios"]:
        assert scenario["simulated"] is True
        assert "simulated" in scenario["notice"].lower()
        assert scenario["title"] and scenario["summary"]
        assert set(scenario) == {"id", "title", "summary", "simulated", "notice"}  # no request leak


def test_running_the_lead_scenario_returns_the_analysis_labelled_simulated(
    client: TestClient,
) -> None:
    response = client.post(RUN + "pune-pivot")
    assert response.status_code == 200
    body = response.json()
    assert body["simulated"] is True
    assert "simulated" in body["notice"].lower()
    assert body["scenario"]["id"] == "pune-pivot"
    analysis = body["analysis"]
    assert analysis["market_coverage"] == "covered"
    assert analysis["ranking"]["recommended_id"] == "custom-celebration-cakes"
    assert [s["tool"] for s in analysis["steps"]][0] == "validate_constraints"


def test_the_other_scenarios_cover_keep_original_nothing_viable_and_no_market_data(
    client: TestClient,
) -> None:
    keep = client.post(RUN + "pune-keep-original").json()["analysis"]["ranking"]
    assert keep["recommended_id"] == "original-cakes" and keep["keep_original"] is True
    none = client.post(RUN + "pune-nothing-viable").json()["analysis"]["ranking"]
    assert none["recommended_id"] is None and none["keep_original"] is False
    noida = client.post(RUN + "noida-feasibility-only").json()["analysis"]
    assert noida["market_coverage"] == "none" and noida["evidence"] == []


@pytest.mark.parametrize("scenario_id", IDS)
def test_a_demo_run_equals_posting_the_same_request_to_analyze(
    client: TestClient, scenario_id: str
) -> None:
    # Same gateway, same service: the demo adds a label, never different numbers.
    from app.services.demo_catalog import load_demo_catalog

    request = load_demo_catalog().request(scenario_id)
    assert request is not None
    direct = client.post("/api/analyze", json=request.model_dump(mode="json")).json()
    assert client.post(RUN + scenario_id).json()["analysis"] == direct


def test_an_unknown_scenario_is_a_generic_404_that_does_not_echo_the_id(
    client: TestClient,
) -> None:
    response = client.post(RUN + "zqsentinel")
    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown demo scenario."}
    assert "zqsentinel" not in response.text


@pytest.mark.parametrize("bad", ["has%20space", "UPPERCASE", "x" * 41, "-lead", "a.b"])
def test_a_malformed_id_is_a_422_without_echoing_it(client: TestClient, bad: str) -> None:
    response = client.post(RUN + bad)
    assert response.status_code == 422
    assert response.json()["detail"] == "The request was not valid."
    assert bad not in response.text and bad.replace("%20", " ") not in response.text


def test_demo_runs_share_the_analyze_rate_limit() -> None:
    clock = FakeClock()
    client = make_client(clock, analyze_rate_limit_per_ip=2, analyze_rate_window_seconds=60)
    assert client.post(RUN + "pune-pivot").status_code == 200
    assert client.post("/api/analyze", json=_body(client)).status_code == 200
    limited = client.post(RUN + "pune-pivot")
    assert limited.status_code == 429
    assert limited.headers["Retry-After"]
    clock.advance(timedelta(seconds=61))
    assert client.post(RUN + "pune-pivot").status_code == 200


def _body(client: TestClient) -> dict[str, Any]:
    from app.services.demo_catalog import load_demo_catalog

    request = load_demo_catalog().request("pune-pivot")
    assert request is not None
    return request.model_dump(mode="json")


def test_a_demo_run_logs_the_outcome_only(
    client: TestClient, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="launchwise.analyze"):
        client.post(RUN + "pune-pivot")
    text = " ".join(r.getMessage() for r in caplog.records)
    assert "analyze outcome=ok" in text
    assert "203.0.113.7" not in text and "Pune" not in text


def test_the_demo_routes_are_get_and_post_only(client: TestClient) -> None:
    assert client.post(LIST_URL).status_code == 405
    assert client.get(RUN + "pune-pivot").status_code == 405
