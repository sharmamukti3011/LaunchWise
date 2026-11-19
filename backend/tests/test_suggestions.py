"""Suggested alternatives: dataset templates become extra options for a user's own idea."""

import json
import re
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError

from app.main import create_app
from app.services.analyze_models import AnalyzeRequest, AnalyzeResponse
from app.services.analyze_service import AnalyzeService
from app.services.demo_catalog import load_demo_catalog
from app.services.explanation_check import validate_summary
from app.services.explanation_facts import build_facts
from app.services.explanation_template import templated_summary
from app.services.market_data import DatasetError, MarketDataset, load_dataset
from app.services.orchestrator import SYSTEM_PROMPT
from app.settings import Settings
from tests.explain_helpers import IDS, analysis_for
from tests.fakes import FakeClock
from tests.pune_fixtures import opportunity

D = Decimal
ID_LIKE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b")
DATASET = Path(__file__).parents[1] / "app" / "data" / "market_opportunities.json"


def sample(category: str = "Home bakery", **overrides: Any) -> dict[str, Any]:
    """Pune, budget 10,000, 3 a day, 2 days a week, original price 500, cost 450, startup 10,000."""
    body: dict[str, Any] = {
        "profile": {
            "budget": "10000", "units_per_day": 3, "days_per_week": 2,
            "skills": [], "equipment": [], "location": "Pune",
        },
        "category": category,
        "suggest_alternatives": True,
        "options": [
            {"id": "original", "title": "Everyday cakes", "is_original": True, "price": "500",
             "variable_cost_per_unit": "450", "fixed_startup_costs": "10000"}
        ],
    }  # fmt: skip
    body.update(overrides)
    return body


def own_alt(option_id: str, title: str, price: str = "600") -> dict[str, Any]:
    return {
        "id": option_id, "title": title, "is_original": False, "price": price,
        "variable_cost_per_unit": "200", "fixed_startup_costs": "1000",
    }  # fmt: skip


def analyze(body: dict[str, Any]) -> AnalyzeResponse:
    request = AnalyzeRequest.model_validate(body)
    return AnalyzeService(load_dataset(), FakeClock()).analyze(request)


def option(result: AnalyzeResponse, option_id: str) -> Any:
    return next(o for o in result.options if o.option_id == option_id)


def totals(result: AnalyzeResponse) -> dict[str, Decimal]:
    return {s.option_id: s.total for s in result.ranking.ranked}


# ---- the dataset's suggestion templates -------------------------------------------------------


def test_the_shipped_dataset_has_one_template_and_keeps_pune_005_as_evidence_only() -> None:
    dataset = load_dataset()
    first = dataset.get("PUNE-001")
    assert first is not None and first.suggestion is not None
    template = first.suggestion
    assert template.title == "Custom celebration cakes"
    assert (template.price.value, template.price.basis) == (D("1200"), "from_source")
    assert template.price.quote is not None and template.price.quote in first.evidence
    for figure in (template.variable_cost, template.startup_cost, template.minutes_per_unit):
        assert figure.basis == "assumption" and figure.quote is None  # the source states none
    # PUNE-005 overlaps PUNE-001 (both are custom cakes), so it stays as evidence, with no template.
    second = dataset.get("PUNE-005")
    assert second is not None and second.suggestion is None
    assert [o.id for o in dataset.opportunities if o.suggestion is not None] == ["PUNE-001"]


def test_no_entry_that_argues_against_an_option_has_a_template() -> None:
    for entry in load_dataset().opportunities:
        if entry.direction == "against":
            assert entry.suggestion is None, entry.id


def test_every_from_source_figure_quotes_text_the_source_really_contains() -> None:
    for entry in load_dataset().opportunities:
        if entry.suggestion is None:
            continue
        template = entry.suggestion
        for figure in (template.price, template.variable_cost, template.startup_cost,
                       template.minutes_per_unit):  # fmt: skip
            if figure.basis == "from_source":
                assert figure.quote and figure.quote in entry.evidence, entry.id
            else:
                assert figure.quote is None, entry.id


def figure(**over: Any) -> dict[str, Any]:
    return {"value": "100", "basis": "assumption"} | over


def template(**over: Any) -> dict[str, Any]:
    data = {
        "title": "A pivot",
        "price": figure(),
        "variable_cost": figure(),
        "startup_cost": figure(),
        "minutes_per_unit": figure(value=60),
    }
    return data | over


def test_a_template_on_an_against_entry_is_rejected() -> None:
    with pytest.raises(ValidationError, match="against"):
        opportunity(direction="against", suggestion=template())


def test_a_from_source_figure_needs_a_quote_that_is_in_the_evidence() -> None:
    quoted = opportunity(evidence="Cakes sell for Rs 900.", suggestion=template(
        price=figure(value="900", basis="from_source", quote="Rs 900")))  # fmt: skip
    assert quoted.suggestion is not None and quoted.suggestion.price.basis == "from_source"
    with pytest.raises(ValidationError, match="quote"):
        opportunity(suggestion=template(price=figure(basis="from_source")))
    with pytest.raises(ValidationError, match="quote"):
        opportunity(evidence="Cakes sell for Rs 900.", suggestion=template(
            price=figure(basis="from_source", quote="Rs 1,200")))  # fmt: skip


def test_an_assumed_figure_must_not_claim_a_quote() -> None:
    with pytest.raises(ValidationError):
        opportunity(suggestion=template(price=figure(basis="assumption", quote="Rs 900")))


@pytest.mark.parametrize(
    "bad",
    [
        {"title": ""},
        {"title": "t" * 81},
        {"price": figure(value="-1")},
        {"price": figure(value="10000001")},
        {"minutes_per_unit": figure(value=1441)},
        {"price": figure(basis="guess")},
        {"extra": 1},
    ],
)
def test_an_invalid_template_is_rejected(bad: dict[str, Any]) -> None:
    with pytest.raises(ValidationError):
        opportunity(suggestion=template(**bad))


def test_the_loader_refuses_a_dataset_with_a_bad_template(tmp_path: Path) -> None:
    data = json.loads(DATASET.read_text())
    data["opportunities"][2]["suggestion"] = {"title": "x"}  # PUNE-003, and incomplete
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(DatasetError):
        load_dataset(path)


# ---- which templates match --------------------------------------------------------------------


@pytest.mark.parametrize("category", ["Home bakery", "bakery", "home bakery", "  HOME   Bakery "])
def test_every_spelling_of_bakery_matches_the_bakery_templates(category: str) -> None:
    found = load_dataset().suggestion_candidates("Pune", category)
    assert [o.id for o in found] == ["PUNE-001"]


@pytest.mark.parametrize(
    ("location", "category"),
    [("Noida", "home bakery"), ("Pune", "web design"), ("", "bakery"), ("Pune", "")],
)
def test_other_places_and_businesses_have_no_candidates(location: str, category: str) -> None:
    assert load_dataset().suggestion_candidates(location, category) == []


def test_pune_maharashtra_counts_as_pune() -> None:
    found = load_dataset().suggestion_candidates("Pune, Maharashtra", "bakery")
    assert len(found) == 1


# ---- adding suggestions to a request ----------------------------------------------------------


def test_with_no_alternative_a_suggestion_is_added_and_linked_to_its_entry() -> None:
    result = analyze(sample())
    suggested = [o for o in result.options if o.is_suggested]
    assert [o.option_id for o in suggested] == ["suggested-pune-001"]
    assert [o.opportunity_id for o in suggested] == ["PUNE-001"]
    assert [o.title for o in suggested] == ["Custom celebration cakes"]
    assert not option(result, "original").is_suggested
    assert {e.id for e in result.evidence} == {"PUNE-001"}


def test_with_one_alternative_there_is_room_for_suggestions_too() -> None:
    body = sample()
    body["options"].append(own_alt("mine", "Cupcake boxes"))
    result = analyze(body)
    assert len([o for o in result.options if o.is_suggested]) == 1
    assert [o.option_id for o in result.options][:2] == ["original", "mine"]


def test_with_two_alternatives_nothing_is_suggested() -> None:
    body = sample()
    for n in (1, 2):
        body["options"].append(own_alt(f"mine-{n}", f"Idea {n}"))
    assert not any(o.is_suggested for o in analyze(body).options)


def test_a_suggestion_with_the_same_title_as_one_of_the_owners_options_is_skipped() -> None:
    body = sample()
    body["options"].append(own_alt("mine", "  custom  CELEBRATION cakes ", "900"))
    assert not any(
        o.is_suggested for o in analyze(body).options
    )  # the only template is a duplicate


def test_a_title_that_duplicates_the_original_idea_is_skipped_too() -> None:
    body = sample()
    body["options"][0]["title"] = "Custom celebration cakes"
    assert not any(o.is_suggested for o in analyze(body).options)


def synthetic_dataset(*titles: str) -> MarketDataset:
    """Three bakery entries that each carry a template, to exercise the cap of two."""
    entries = [
        opportunity(
            id=f"TEST-FAKE-00{n}",
            suggestion=template(title=title, price=figure(value="900")),
        )
        for n, title in enumerate(titles, start=1)
    ]
    return MarketDataset(entries)


def analyze_with(dataset: MarketDataset, body: dict[str, Any]) -> AnalyzeResponse:
    return AnalyzeService(dataset, FakeClock()).analyze(AnalyzeRequest.model_validate(body))


def test_at_most_two_suggestions_are_added_however_many_templates_match() -> None:
    dataset = synthetic_dataset("First pivot", "Second pivot", "Third pivot")
    result = analyze_with(dataset, sample())
    assert [o.title for o in result.options if o.is_suggested] == ["First pivot", "Second pivot"]


def test_a_duplicate_title_is_skipped_and_the_next_template_takes_its_place() -> None:
    dataset = synthetic_dataset("First pivot", "Second pivot", "Third pivot")
    body = sample()
    body["options"].append(own_alt("mine", "first PIVOT"))
    result = analyze_with(dataset, body)
    assert [o.title for o in result.options if o.is_suggested] == ["Second pivot", "Third pivot"]


def test_nothing_is_suggested_unless_the_request_asks_for_it() -> None:
    body = sample()
    del body["suggest_alternatives"]
    assert not any(o.is_suggested for o in analyze(body).options)
    assert not any(o.is_suggested for o in analyze(sample(suggest_alternatives=False)).options)


def test_nothing_is_suggested_outside_covered_places_and_businesses() -> None:
    assert not any(o.is_suggested for o in analyze(sample("web design")).options)
    body = sample()
    body["profile"]["location"] = "Noida"
    assert not any(o.is_suggested for o in analyze(body).options)


def test_a_client_cannot_mark_its_own_option_as_suggested() -> None:
    body = sample()
    body["options"][0]["is_suggested"] = True
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate(body)


@pytest.mark.parametrize("scenario", IDS)
def test_the_guided_demo_scenarios_are_unchanged(scenario: str) -> None:
    request = load_demo_catalog().request(scenario)
    assert request is not None and request.suggest_alternatives is False
    result = analysis_for(scenario)
    assert not any(o.is_suggested for o in result.options)
    assert not any(s.tool == "suggest_alternatives" for s in result.steps)


# ---- scored by the same engine ----------------------------------------------------------------


def test_the_samples_scores_are_worked_out_by_the_same_rules() -> None:
    result = analyze(sample())
    scores = {o.option_id: {s.dimension: s.score for s in o.score.scores} for o in result.options}
    # Original: price 500, cost 450 -> margin 50 = 10% -> 10/50*100 = 20.
    #   budget: 10,000 + 450*6 = 12,700 against 10,000 -> over budget -> 0.
    #   capacity: assumed 60 min * 6 = 6 h <= assumed 20 h -> 100. skills/equipment -> 100.
    #   market: no evidence -> 50.   total = (20*30 + 0*20 + 100*20 + 100*15 + 50*15) / 100 = 48.50
    assert scores["original"] == {"margin": 20, "budget": 0, "capacity": 100,
                                  "skill_equipment": 100, "market_signal": 50}  # fmt: skip
    # PUNE-001 (price 1,200 from the source; cost 500, startup 4,000, 100 min assumed):
    #   margin 700 = 58.33% -> capped at 100. budget: 4,000 + 500*6 = 7,000; headroom 3,000 = 30%
    #   -> 80. capacity: 100 min * 6 = 10 h <= 20 h -> 100. skills 100. market: verified medium 60.
    #   total = (100*30 + 80*20 + 100*20 + 100*15 + 60*15) / 100 = 9000 / 100 = 90.00
    assert scores["suggested-pune-001"] == {
        "margin": 100, "budget": 80, "capacity": 100, "skill_equipment": 100, "market_signal": 60,
    }  # fmt: skip
    assert totals(result) == {"suggested-pune-001": D("90.00"), "original": D("48.50")}


def test_the_sample_recommends_a_suggestion_because_the_original_is_over_budget() -> None:
    result = analyze(sample())
    assert [s.option_id for s in result.ranking.ranked] == ["suggested-pune-001", "original"]
    assert result.ranking.recommended_id == "suggested-pune-001"
    original = next(s for s in result.ranking.ranked if s.option_id == "original")
    assert not original.viable and "over budget" in original.viability_issues


def test_a_suggestion_can_lose_to_the_owners_own_idea() -> None:
    body = sample()
    body["options"][0] |= {"price": "1500", "variable_cost_per_unit": "200",
                           "fixed_startup_costs": "500"}  # fmt: skip
    result = analyze(body)
    assert result.ranking.recommended_id == "original" and result.ranking.keep_original is True
    assert all(s.total < totals(result)["original"] for s in result.ranking.ranked[1:])


def test_a_suggestion_can_be_not_viable() -> None:
    body = sample()
    body["profile"]["budget"] = "1000"  # far too little for any startup cost
    result = analyze(body)
    for o in result.options:
        assert o.score.viable is False and "over budget" in o.score.viability_issues
    assert result.ranking.recommended_id is None


def test_the_score_rows_say_which_options_are_suggestions() -> None:
    result = analyze(sample())
    flags = {s.option_id: s.is_suggested for s in result.ranking.ranked}
    assert flags == {"suggested-pune-001": True, "original": False}


# ---- honest provenance ------------------------------------------------------------------------


def test_the_suggestion_lists_each_figure_with_where_it_comes_from() -> None:
    suggestion = option(analyze(sample()), "suggested-pune-001").suggestion
    assert suggestion is not None
    assert suggestion.source_name == "YourStory (HerStory)"
    by_field = {f.field: f for f in suggestion.figures}
    assert set(by_field) == {"price", "variable_cost", "startup_cost", "minutes_per_unit"}
    assert (by_field["price"].value, by_field["price"].basis) == ("1200", "from_source")
    assert by_field["price"].quote is not None
    for name in ("variable_cost", "startup_cost", "minutes_per_unit"):
        assert by_field[name].basis == "assumption"
    assert option(analyze(sample()), "original").suggestion is None


def test_the_engine_does_not_call_an_assumed_figure_user_provided() -> None:
    feasibility = option(analyze(sample()), "suggested-pune-001").feasibility
    assert feasibility.inputs.price.source == "from_source"
    assert feasibility.inputs.variable_cost_per_unit.source == "assumption"
    assert feasibility.inputs.fixed_startup_costs.source == "assumption"
    assert feasibility.startup_cost.source == "assumption"
    assert feasibility.unit_variable_cost.source == "assumption"
    assert feasibility.budget_check.startup_cost.source == "assumption"
    # The owner's own figures stay theirs.
    assert feasibility.inputs.budget.source == "user_provided"
    assert feasibility.inputs.units_per_day.source == "user_provided"
    assert option(analyze(sample()), "original").feasibility.startup_cost.source == "user_provided"


def test_a_figure_from_the_source_is_not_flagged_as_an_assumption_caveat() -> None:
    result = analyze(sample())
    assert option(result, "suggested-pune-001").opportunity_id == "PUNE-001"
    assert option(result, "suggested-pune-001").suggestion.figures[0].basis == "from_source"


# ---- caveats, steps ---------------------------------------------------------------------------


def suggestion_caveats(result: AnalyzeResponse) -> list[str]:
    return [c.message for c in result.ranking.caveats if c.kind == "suggestion"]


def test_there_is_one_caveat_line_per_suggestion_saying_its_figures_are_partly_assumed() -> None:
    messages = suggestion_caveats(analyze(sample()))
    assert len(messages) == 1
    first = messages[0]
    assert first.startswith("Custom celebration cakes")
    assert "suggestion" in first and "price comes from YourStory (HerStory)" in first
    assert "assumed" in first and "variable cost" in first and "startup cost" in first
    assert all("assumed" in m for m in messages)


def test_the_suggestion_caveats_show_even_when_the_recommendation_is_the_owners_idea() -> None:
    body = sample()
    body["options"][0] |= {"price": "1500", "variable_cost_per_unit": "200",
                           "fixed_startup_costs": "500"}  # fmt: skip
    result = analyze(body)
    assert result.ranking.recommended_id == "original"
    assert len(suggestion_caveats(result)) == 1


def test_the_suggestion_caveats_never_show_a_dataset_id_or_repeat() -> None:
    messages = suggestion_caveats(analyze(sample()))
    assert len(messages) == len(set(messages))
    assert not any(ID_LIKE.search(m) for m in messages)


def test_a_suggestion_step_is_added_only_when_something_was_suggested() -> None:
    result = analyze(sample())
    names = [s.tool for s in result.steps]
    assert names.count("suggest_alternatives") == 1
    assert [s.index for s in result.steps] == list(range(1, len(result.steps) + 1))
    step = next(s for s in result.steps if s.tool == "suggest_alternatives")
    assert (
        step.title.startswith("Suggested 1 alternative from")
        and "Custom celebration cakes" in step.title
    )
    assert "suggest_alternatives" not in [
        s.tool for s in analyze(sample(suggest_alternatives=False)).steps
    ]


# ---- Claude and the template explain a suggestion ---------------------------------------------


def test_the_facts_say_when_an_option_is_a_suggestion() -> None:
    facts = build_facts(analyze(sample()))
    assert facts["recommended"]["is_suggestion"] is True
    assert {r["title"]: r["is_suggested"] for r in facts["ranked"]}["Everyday cakes"] is False


def test_the_prompt_tells_claude_to_say_when_the_recommendation_is_a_suggestion() -> None:
    assert "suggest" in SYSTEM_PROMPT.lower() and "not the owner's own idea" in SYSTEM_PROMPT


def test_the_template_says_the_recommended_option_is_a_suggestion_and_passes_the_check() -> None:
    result = analyze(sample())
    text = templated_summary(result)
    assert "a suggestion from LaunchWise" in text and "not your own idea" in text
    assert validate_summary(text, result) is None


def test_the_template_does_not_mention_suggestions_when_the_owners_idea_is_recommended() -> None:
    body = sample()
    body["options"][0] |= {"price": "1500", "variable_cost_per_unit": "200",
                           "fixed_startup_costs": "500"}  # fmt: skip
    result = analyze(body)
    assert "suggestion" not in templated_summary(result).lower()


GOOD = (
    "The engine recommends Custom celebration cakes, a suggestion from LaunchWise rather than "
    "your own idea, which scored 90.00 out of 100. Your own idea, Everyday cakes, is over budget "
    "and scored 48.50. Some of the suggestion's figures are assumed, and nothing here is a "
    "promise of profit."
)


def test_the_check_requires_saying_a_recommended_suggestion_is_one() -> None:
    result = analyze(sample())
    assert validate_summary(GOOD, result) is None
    silent = GOOD.replace(", a suggestion from LaunchWise rather than your own idea,", "")
    silent = silent.replace(
        "Some of the suggestion's figures are assumed", "Some figures are assumed"
    )
    problem = validate_summary(silent, result)
    assert problem is not None and "suggestion" in problem


def test_the_number_and_source_checks_still_apply_to_a_suggestion_summary() -> None:
    result = analyze(sample())
    assert "not in the facts" in (validate_summary(GOOD.replace("90.00", "91.00"), result) or "")
    assert "not in the facts" in (
        validate_summary(GOOD + " Evidence from Swiggy agrees.", result) or ""
    )


def test_the_explain_route_works_for_a_request_with_suggestions() -> None:
    settings = Settings(_env_file=None, app_env="test")
    client = TestClient(create_app(settings), client=("203.0.113.9", 5000))
    response = client.post("/api/analyze/explain", json=sample())
    assert response.status_code == 200
    summary = response.json()["explanation"]["summary"]
    assert "Custom celebration cakes" in summary and "suggestion" in summary
