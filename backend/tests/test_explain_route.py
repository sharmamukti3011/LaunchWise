"""POST /api/demo/explain/{id}: Claude's explanation of a seeded scenario, with a safe fallback."""

from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.settings import Settings
from tests.explain_helpers import GOOD, reply
from tests.fakes import FakeClaude, FakeClock

URL = "/api/demo/explain/"


def make_client(
    claude: FakeClaude | None = None, clock: FakeClock | None = None, **overrides: Any
) -> TestClient:
    settings = Settings(_env_file=None, app_env="test", **overrides)
    app = create_app(settings, clock=clock, claude=claude)
    return TestClient(app, client=("203.0.113.7", 50000))


def test_without_a_key_the_demo_still_explains_with_the_template() -> None:
    response = make_client().post(URL + "pune-pivot")
    assert response.status_code == 200
    body = response.json()
    assert body["simulated"] is True and body["scenario_id"] == "pune-pivot"
    explanation = body["explanation"]
    assert (
        explanation["source"] == "template" and explanation["fallback_reason"] == "not_configured"
    )
    assert "Custom celebration cakes" in explanation["summary"]


def test_with_claude_the_explanation_is_claudes_and_labelled_as_such() -> None:
    fake = FakeClaude(reply(GOOD))
    body = make_client(fake).post(URL + "pune-pivot").json()
    assert body["explanation"] == {"summary": GOOD, "source": "claude", "fallback_reason": None}
    assert len(fake.calls) == 1


def test_claude_failure_never_breaks_the_endpoint() -> None:
    from app.services.orchestrator import ClaudeUnavailable

    body = make_client(FakeClaude(ClaudeUnavailable("down"))).post(URL + "pune-pivot").json()
    assert body["explanation"]["source"] == "template"
    assert body["explanation"]["fallback_reason"] == "unavailable"


@pytest.mark.parametrize(
    "scenario",
    ["pune-pivot", "pune-keep-original", "pune-nothing-viable", "noida-feasibility-only"],
)
def test_every_seeded_scenario_can_be_explained(scenario: str) -> None:
    assert make_client().post(URL + scenario).status_code == 200


def test_the_session_cap_comes_from_settings() -> None:
    fake = FakeClaude(reply(GOOD))
    client = make_client(fake, claude_max_calls_per_session=1)
    assert client.post(URL + "pune-pivot").json()["explanation"]["source"] == "claude"
    second = client.post(URL + "pune-pivot").json()["explanation"]
    assert second["source"] == "template" and second["fallback_reason"] == "budget"
    assert len(fake.calls) == 1


def test_the_global_cap_comes_from_settings() -> None:
    fake = FakeClaude(reply(GOOD))
    client = make_client(fake, claude_max_calls_global=1)
    assert client.post(URL + "pune-pivot").json()["explanation"]["source"] == "claude"
    assert client.post(URL + "pune-pivot").json()["explanation"]["fallback_reason"] == "budget"


def test_an_unknown_scenario_is_a_generic_404_without_a_claude_call() -> None:
    fake = FakeClaude()
    response = make_client(fake).post(URL + "zqsentinel")
    assert response.status_code == 404
    assert response.json() == {"detail": "Unknown demo scenario."}
    assert fake.calls == []


@pytest.mark.parametrize("bad", ["has%20space", "UPPERCASE", "x" * 41, "-lead"])
def test_a_malformed_id_is_a_422_without_a_claude_call(bad: str) -> None:
    fake = FakeClaude()
    assert make_client(fake).post(URL + bad).status_code == 422
    assert fake.calls == []


def test_explain_shares_the_analyze_rate_limit() -> None:
    clock = FakeClock()
    client = make_client(clock=clock, analyze_rate_limit_per_ip=2, analyze_rate_window_seconds=60)
    assert client.post(URL + "pune-pivot").status_code == 200
    assert client.post(URL + "pune-pivot").status_code == 200
    limited = client.post(URL + "pune-pivot")
    assert limited.status_code == 429 and limited.headers["Retry-After"]
    clock.advance(timedelta(seconds=61))
    assert client.post(URL + "pune-pivot").status_code == 200


def test_get_is_not_allowed() -> None:
    assert make_client().get(URL + "pune-pivot").status_code == 405


def test_the_response_never_contains_credentials() -> None:
    client = make_client(FakeClaude(reply(GOOD)), anthropic_api_key="sk-ant-test-secret")
    assert "sk-ant-test-secret" not in client.post(URL + "pune-pivot").text
