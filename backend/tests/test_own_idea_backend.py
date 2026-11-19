"""Backend for 'Try your own idea': assumed defaults, evidence choices, explaining any request."""

import json
import logging
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.analyze_models import (
    DEFAULT_HOURS_PER_WEEK,
    DEFAULT_MINUTES_PER_UNIT,
    AnalyzeRequest,
)
from app.services.analyze_service import AnalyzeService
from app.services.demo_catalog import load_demo_catalog
from app.services.market_data import load_dataset
from app.settings import Settings
from tests.explain_helpers import GOOD, reply
from tests.fakes import FakeClaude, FakeClock

EXPLAIN = "/api/analyze/explain"
EVIDENCE = "/api/market-evidence"
SENTINEL = "ZQSENTINEL"
CLIENT = "198.51.100.88"


def demo_body(scenario: str = "pune-pivot") -> dict[str, Any]:
    request = load_demo_catalog().request(scenario)
    assert request is not None
    return request.model_dump(mode="json")


def make_client(
    claude: FakeClaude | None = None, clock: FakeClock | None = None, **cfg: Any
) -> TestClient:
    settings = Settings(_env_file=None, app_env="test", **cfg)
    return TestClient(create_app(settings, clock=clock, claude=claude), client=(CLIENT, 50000))


# ---- assumed defaults -------------------------------------------------------------------------


def without(body: dict[str, Any], *, hours: bool = False, minutes: bool = False) -> dict[str, Any]:
    if hours:
        del body["profile"]["hours_per_week"]
    if minutes:
        for option in body["options"]:
            del option["minutes_per_unit"]
    return body


def test_the_defaults_are_named_assumptions() -> None:
    assert (DEFAULT_HOURS_PER_WEEK, DEFAULT_MINUTES_PER_UNIT) == (20, 60)


def test_a_missing_weekly_hours_figure_becomes_a_tagged_assumption() -> None:
    request = AnalyzeRequest.model_validate(without(demo_body(), hours=True))
    assert request.profile.hours_per_week.value == DEFAULT_HOURS_PER_WEEK
    assert request.profile.hours_per_week.source == "assumption"


def test_a_missing_time_per_item_becomes_a_tagged_assumption() -> None:
    request = AnalyzeRequest.model_validate(without(demo_body(), minutes=True))
    for option in request.options:
        assert option.minutes_per_unit.value == DEFAULT_MINUTES_PER_UNIT
        assert option.minutes_per_unit.source == "assumption"


def test_values_the_owner_gave_are_kept_and_stay_user_provided() -> None:
    body = demo_body()
    body["profile"]["hours_per_week"] = {"value": 8, "source": "user_provided"}
    body["options"][0]["minutes_per_unit"] = {"value": 45, "source": "user_provided"}
    request = AnalyzeRequest.model_validate(body)
    assert (request.profile.hours_per_week.value, request.profile.hours_per_week.source) == (
        8,
        "user_provided",
    )
    assert request.options[0].minutes_per_unit.value == 45


@pytest.mark.parametrize("where", ["hours", "minutes"])
def test_an_explicit_null_is_still_rejected(where: str) -> None:
    body = demo_body()
    if where == "hours":
        body["profile"]["hours_per_week"] = None
    else:
        body["options"][0]["minutes_per_unit"] = None
    with pytest.raises(ValueError):
        AnalyzeRequest.model_validate(body)


def test_the_engines_existing_caveats_flag_the_assumed_defaults() -> None:
    request = AnalyzeRequest.model_validate(
        without(demo_body("pune-keep-original"), hours=True, minutes=True)
    )
    result = AnalyzeService(load_dataset(), FakeClock()).analyze(request)
    messages = [c.message for c in result.ranking.caveats]
    # Two options are compared, so each assumed input names the recommended option.
    title = next(o.title for o in result.options if o.option_id == result.ranking.recommended_id)
    assert "Weekly hours available (20) is assumed, not provided by you" in messages  # never named
    assert f"{title}: time per item (60 minutes) is assumed, not provided by you" in messages


def test_the_route_accepts_a_request_with_the_two_figures_left_out() -> None:
    body = without(demo_body(), hours=True, minutes=True)
    response = make_client().post("/api/analyze", json=body)
    assert response.status_code == 200
    assert response.json()["profile"]["hours_per_week"] == {"value": 20, "source": "assumption"}


# ---- evidence choices for an alternative ------------------------------------------------------


def test_the_evidence_choices_list_every_dataset_entry_with_only_what_a_picker_needs() -> None:
    response = make_client().get(EVIDENCE)
    assert response.status_code == 200
    entries = response.json()["evidence"]
    assert [e["id"] for e in entries] == [f"PUNE-00{n}" for n in range(1, 6)]
    for entry in entries:
        assert set(entry) == {"id", "title", "source_name", "direction"}
    assert {e["id"]: e["direction"] for e in entries}["PUNE-003"] == "against"


def test_the_evidence_choices_are_read_only() -> None:
    assert make_client().post(EVIDENCE).status_code == 405


# ---- explaining a request that is not a demo scenario -----------------------------------------


def test_any_request_can_be_explained_and_the_analysis_is_recomputed_on_the_server() -> None:
    fake = FakeClaude(reply(GOOD))
    response = make_client(fake).post(EXPLAIN, json=demo_body())
    assert response.status_code == 200
    explanation = response.json()["explanation"]
    assert explanation == {"summary": GOOD, "source": "claude", "fallback_reason": None}
    facts = fake.calls[0][1][0]["content"]
    assert "Custom celebration cakes" in facts  # the engine's own result


def test_without_claude_the_template_is_used() -> None:
    explanation = make_client().post(EXPLAIN, json=demo_body()).json()["explanation"]
    assert explanation["source"] == "template"
    assert explanation["fallback_reason"] == "not_configured"
    assert "Custom celebration cakes" in explanation["summary"]


def test_a_feasibility_only_request_can_be_explained() -> None:
    response = make_client().post(EXPLAIN, json=demo_body("noida-feasibility-only"))
    assert response.status_code == 200 and response.json()["explanation"]["summary"]


def test_an_invalid_request_is_a_generic_422_and_claude_is_never_called() -> None:
    fake = FakeClaude()
    body = demo_body()
    body["profile"]["budget"] = "-5"
    response = make_client(fake).post(EXPLAIN, json=body)
    assert response.status_code == 422 and response.json()["detail"] == "The request was not valid."
    assert fake.calls == []


def test_explain_shares_the_analyze_rate_limit_and_the_claude_caps() -> None:
    fake = FakeClaude(reply(GOOD))
    client = make_client(fake, claude_max_calls_per_session=1)
    assert client.post(EXPLAIN, json=demo_body()).json()["explanation"]["source"] == "claude"
    second = client.post(EXPLAIN, json=demo_body()).json()["explanation"]
    assert second["source"] == "template" and second["fallback_reason"] == "budget"
    limited = make_client(analyze_rate_limit_per_ip=1)
    assert limited.post(EXPLAIN, json=demo_body()).status_code == 200
    assert limited.post(EXPLAIN, json=demo_body()).status_code == 429


def test_the_request_body_is_capped_at_32_kb() -> None:
    client = make_client()
    padded = json.dumps(demo_body()).encode() + b" " * (32 * 1024)
    response = client.post(EXPLAIN, content=padded, headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_get_is_not_allowed_on_explain() -> None:
    assert make_client().get(EXPLAIN).status_code == 405


def test_a_sentinel_in_the_ideas_text_never_reaches_a_response_or_a_log(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    body = demo_body()
    body["options"][0]["title"] = f"{SENTINEL} cakes"
    body["category"] = f"home bakery {SENTINEL}"
    fake = FakeClaude("not json", "still not json")  # forces the fallback path too
    response = make_client(fake).post(EXPLAIN, json=body)
    assert response.status_code == 200
    assert SENTINEL not in caplog.text and CLIENT not in caplog.text
    bad = dict(body, profile={**body["profile"], "budget": f"{SENTINEL}"})
    assert SENTINEL not in make_client().post(EXPLAIN, json=bad).text


# ---- an alternative may have no market evidence, even in a covered area -----------------------


def test_the_route_accepts_an_alternative_with_no_evidence_link_in_pune() -> None:
    body = demo_body("pune-pivot")
    del body["options"][1]["opportunity_id"]  # the custom cakes, no longer linked
    response = make_client().post("/api/analyze", json=body)
    assert response.status_code == 200
    custom = next(
        o for o in response.json()["options"] if o["option_id"] == "custom-celebration-cakes"
    )
    market = next(s for s in custom["score"]["scores"] if s["dimension"] == "market_signal")
    assert market["score"] == 50 and custom["opportunity_id"] is None


def test_an_unknown_evidence_id_is_still_rejected_with_the_field_named() -> None:
    body = demo_body("pune-pivot")
    body["options"][1]["opportunity_id"] = "PUNE-999"
    response = make_client().post("/api/analyze", json=body)
    assert response.status_code == 422
    assert response.json()["errors"] == [
        {
            "field": "options.1.opportunity_id",
            "message": "An option links to market evidence that is not in the dataset.",
        }
    ]


def test_the_alternative_with_no_evidence_is_explained_without_naming_any_source() -> None:
    body = demo_body("pune-pivot")
    del body["options"][1]["opportunity_id"]
    explanation = make_client().post(EXPLAIN, json=body).json()["explanation"]
    assert explanation["source"] == "template"
    assert "Custom celebration cakes" in explanation["summary"]
