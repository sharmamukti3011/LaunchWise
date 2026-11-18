"""AnalyzeService: deterministic analysis, coverage handling, and the step log."""

import json
from datetime import UTC, date, datetime
from decimal import Decimal
from typing import Any

import pytest

from app.services.analyze_models import AnalyzeRequest, AnalyzeResponse
from app.services.analyze_service import AnalyzeService, ScenarioError
from app.services.compare_strategies import compare_strategies, feasibility_for
from app.services.market_data import MarketDataset
from tests.fakes import FakeClock
from tests.pune_fixtures import opportunity

D = Decimal
SENTINEL_ID = "zz-sentinel-id"
# Keys that would make output depend on when or how long it ran. (lead_time_days is dataset data.)
TIME_KEYS = {
    "timestamp",
    "duration",
    "duration_ms",
    "elapsed",
    "started_at",
    "finished_at",
    "created_at",
}  # noqa: E501


def dataset() -> MarketDataset:
    return MarketDataset(
        [
            opportunity(id="TEST-FAKE-001"),
            opportunity(
                id="TEST-FAKE-002",
                verification_status="unverified_sample",
                verified_by=None,
                verified_on=None,
                signal_strength="low",
            ),
        ]
    )


def service(clock: FakeClock | None = None) -> AnalyzeService:
    return AnalyzeService(dataset(), clock or FakeClock())


def profile(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "budget": "10000",
        "units_per_day": 3,
        "days_per_week": 2,
        "hours_per_week": {"value": 12, "source": "assumption"},
        "skills": ["baking", "decorating"],
        "equipment": ["oven", "mixer"],
        "location": "Pune",
    }
    data.update(overrides)
    return data


def option(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "original-cakes",
        "title": "Everyday cakes",
        "is_original": True,
        "price": "800",
        "variable_cost_per_unit": "350",
        "fixed_startup_costs": "6000",
        "minutes_per_unit": {"value": 90, "source": "assumption"},
        "required_skills": ["baking"],
        "required_equipment": ["oven"],
    }
    data.update(overrides)
    return data


def alternative(n: int = 1, link: str | None = "TEST-FAKE-001", **overrides: Any) -> dict[str, Any]:
    data = option(
        id=f"alt-{n}",
        title=f"Alternative {n}",
        is_original=False,
        price="1200",
        variable_cost_per_unit="300",
        fixed_startup_costs="4000",
        **overrides,
    )
    if link is not None:
        data["opportunity_id"] = link
    return data


def request(**overrides: Any) -> AnalyzeRequest:
    data: dict[str, Any] = {
        "profile": profile(),
        "category": "home bakery",
        "options": [option(), alternative()],
    }
    data.update(overrides)
    return AnalyzeRequest.model_validate(data)


def analyze(req: AnalyzeRequest | None = None, clock: FakeClock | None = None) -> AnalyzeResponse:
    return service(clock).analyze(req or request())


# ---- covered scenarios ------------------------------------------------------------------------


def test_a_covered_scenario_returns_profile_numbers_ranking_and_evidence() -> None:
    req = request()
    result = analyze(req)
    assert result.market_coverage == "covered"
    assert result.profile == req.profile
    assert [o.option_id for o in result.options] == ["original-cakes", "alt-1"]
    assert result.skipped_option_ids == []
    assert [e.id for e in result.evidence] == ["TEST-FAKE-001"]
    assert result.market_message


def test_numbers_come_from_the_engine_unchanged() -> None:
    req = request()
    result = analyze(req)
    for analysis, opt in zip(result.options, req.options, strict=True):
        assert analysis.feasibility == feasibility_for(req.profile, opt)


def test_the_ranking_is_exactly_what_compare_strategies_returns() -> None:
    req = request()
    expected = compare_strategies(
        req.profile, list(req.options), list(dataset().opportunities), date(2026, 11, 17)
    )
    assert analyze(req).ranking == expected


def test_each_option_carries_its_own_score() -> None:
    result = analyze()
    ranked = {s.option_id: s for s in result.ranking.ranked}
    for analysis in result.options:
        assert analysis.score == ranked[analysis.option_id]


@pytest.mark.parametrize("location", ["Pune", " pune ", "PUNE", "Pune, Maharashtra", "Pune City"])
@pytest.mark.parametrize("category", ["bakery", "Home Bakery", " home bakery "])
def test_location_and_category_variants_are_covered(location: str, category: str) -> None:
    req = request(profile=profile(location=location), category=category)
    assert analyze(req).market_coverage == "covered"


def test_an_original_only_request_still_works_when_covered() -> None:
    result = analyze(request(options=[option()]))
    assert result.market_coverage == "covered"
    assert [o.option_id for o in result.options] == ["original-cakes"]
    assert result.evidence == []


def test_evidence_lists_only_entries_the_options_link_to_once() -> None:
    req = request(
        options=[option(), alternative(1, "TEST-FAKE-002"), alternative(2, "TEST-FAKE-002")]
    )
    assert [e.id for e in analyze(req).evidence] == ["TEST-FAKE-002"]


def test_unverified_evidence_is_called_out_in_the_message_and_caveats() -> None:
    req = request(options=[option(), alternative(1, "TEST-FAKE-002")])
    result = analyze(req)
    assert "unverified" in result.market_message.lower()
    recommended = result.ranking.recommended_id
    if recommended == "alt-1":
        assert any(c.kind == "verification" for c in result.ranking.caveats)


# ---- determinism, steps -----------------------------------------------------------------------


def test_the_same_request_gives_byte_identical_output() -> None:
    first = analyze().model_dump_json()
    assert analyze().model_dump_json() == first
    assert service().analyze(request()).model_dump_json() == first


def test_steps_follow_the_tool_order_with_sequential_indexes() -> None:
    result = analyze()
    assert [s.tool for s in result.steps] == [
        "validate_constraints",
        "query_market_opportunities",
        "run_feasibility",
        "run_feasibility",
        "compare_strategies",
    ]
    assert [s.index for s in result.steps] == [1, 2, 3, 4, 5]
    assert all(s.status == "ok" and s.title for s in result.steps)


def test_step_results_carry_the_real_figures() -> None:
    req = request()
    result = analyze(req)
    validate, market, feas1, feas2, compare = result.steps
    assert validate.tool == "validate_constraints" and validate.result.profile == req.profile
    assert market.tool == "query_market_opportunities"
    assert market.input.location == "Pune" and market.result.coverage == "covered"
    assert market.result.linked_ids == ["TEST-FAKE-001"]
    assert feas1.tool == "run_feasibility" and feas1.input.option_id == "original-cakes"
    assert feas1.result == result.options[0].feasibility
    assert feas2.tool == "run_feasibility" and feas2.result == result.options[1].feasibility
    assert compare.tool == "compare_strategies"
    assert compare.result.ranked_ids == [s.option_id for s in result.ranking.ranked]
    assert compare.result.recommended_id == result.ranking.recommended_id


def test_the_output_has_no_timestamps_and_money_is_never_a_float() -> None:
    payload = json.loads(analyze().model_dump_json())

    def walk(node: Any) -> None:
        assert not isinstance(node, float), "money and figures must not be floats"
        if isinstance(node, dict):
            for key, value in node.items():
                assert key not in TIME_KEYS, key
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(payload)
    assert payload["analyzed_on"] == "2026-11-17"


def test_analyzed_on_uses_india_time() -> None:
    late_utc = FakeClock(datetime(2026, 11, 17, 20, 0, tzinfo=UTC))  # 01:30 on the 18th in India
    assert analyze(clock=late_utc).analyzed_on == date(2026, 11, 18)
    early_utc = FakeClock(datetime(2026, 11, 17, 5, 0, tzinfo=UTC))  # 10:30 on the 17th
    assert analyze(clock=early_utc).analyzed_on == date(2026, 11, 17)


def test_an_event_that_passed_in_india_time_makes_the_option_non_viable() -> None:
    data = MarketDataset([opportunity(id="TEST-FAKE-001", event_date=date(2026, 11, 17))])
    req = request(options=[option(), alternative()])
    same_day = AnalyzeService(data, FakeClock(datetime(2026, 11, 17, 5, 0, tzinfo=UTC)))
    next_day_in_india = AnalyzeService(data, FakeClock(datetime(2026, 11, 17, 20, 0, tzinfo=UTC)))
    alt_same_day = next(s for s in same_day.analyze(req).ranking.ranked if s.option_id == "alt-1")
    alt_next_day = next(
        s for s in next_day_in_india.analyze(req).ranking.ranked if s.option_id == "alt-1"
    )  # noqa: E501
    assert alt_same_day.viable
    assert not alt_next_day.viable and "event passed" in alt_next_day.viability_issues


# ---- no coverage: feasibility only ------------------------------------------------------------


def noida_request(**overrides: Any) -> AnalyzeRequest:
    data: dict[str, Any] = {
        "profile": profile(
            location="Noida, Uttar Pradesh",
            budget="50000",
            units_per_day=40,
            days_per_week=6,
            hours_per_week={"value": 40, "source": "user_provided"},
            skills=["cooking"],
            equipment=["induction stove"],
        ),
        "category": "high-protein breakfast",
        "options": [
            option(
                id="protein-box",
                title="High-protein breakfast boxes",
                price="150",
                variable_cost_per_unit="80",
                fixed_startup_costs="15000",
                minutes_per_unit={"value": 8, "source": "user_provided"},
                required_skills=["cooking"],
                required_equipment=["induction stove"],
            ),
            alternative(1, "TEST-FAKE-001"),
        ],
    }
    data.update(overrides)
    return AnalyzeRequest.model_validate(data)


def test_outside_the_dataset_coverage_the_analysis_is_feasibility_only() -> None:
    result = analyze(noida_request())
    assert result.market_coverage == "none"
    assert "feasibility-only" in result.market_message
    assert "no market evidence" in result.market_message.lower()
    assert [o.option_id for o in result.options] == ["protein-box"]
    assert result.skipped_option_ids == ["alt-1"]  # not compared, and the response says so
    assert result.evidence == []  # no invented evidence


def test_feasibility_numbers_are_present_for_the_original() -> None:
    req = noida_request()
    result = analyze(req)
    numbers = result.options[0].feasibility
    assert numbers == feasibility_for(req.profile, req.options[0])
    assert numbers.weekly_capacity.value == 240
    assert numbers.contribution_margin.value == D("70.00")


def test_the_original_can_still_be_recommended_with_no_pivot() -> None:
    result = analyze(noida_request())
    assert result.ranking.recommended_id == "protein-box"
    assert result.ranking.keep_original is True
    assert [s.option_id for s in result.ranking.ranked] == ["protein-box"]


def test_the_market_signal_is_a_neutral_50_labelled_no_market_evidence() -> None:
    result = analyze(noida_request())
    signal = next(s for s in result.options[0].score.scores if s.dimension == "market_signal")
    assert signal.score == 50
    assert "no market evidence" in signal.reason
    assert any(c.kind == "no_market_evidence" for c in result.ranking.caveats)
    assert not any(c.kind == "verification" for c in result.ranking.caveats)


def test_a_market_link_on_the_original_is_ignored_when_there_is_no_coverage() -> None:
    req = noida_request()
    linked = req.options[0].model_copy(update={"opportunity_id": "TEST-FAKE-001"})
    result = analyze(req.model_copy(update={"options": [linked, req.options[1]]}))
    assert result.market_coverage == "none"
    assert result.evidence == []
    signal = next(s for s in result.options[0].score.scores if s.dimension == "market_signal")
    assert signal.score == 50


def test_the_no_coverage_steps_say_so_and_skip_the_alternatives() -> None:
    result = analyze(noida_request())
    assert [s.tool for s in result.steps] == [
        "validate_constraints",
        "query_market_opportunities",
        "run_feasibility",
        "compare_strategies",
    ]
    market = result.steps[1]
    assert market.tool == "query_market_opportunities"
    assert market.result.coverage == "none" and market.result.linked_ids == []
    assert "feasibility only" in market.title.lower()


def test_a_non_viable_original_in_a_no_coverage_scenario_gets_no_recommendation() -> None:
    req = noida_request(profile=profile(location="Noida", budget="100"))
    result = analyze(req)
    assert result.ranking.recommended_id is None and result.ranking.keep_original is False
    assert result.market_coverage == "none"


def test_a_pune_bakery_is_not_mistaken_for_noida() -> None:
    assert analyze(request(profile=profile(location="Pune"))).market_coverage == "covered"
    assert analyze(request(profile=profile(location="Noida"))).market_coverage == "none"
    assert analyze(request(category="high-protein breakfast")).market_coverage == "none"


# ---- links must match the dataset -------------------------------------------------------------


def test_an_unknown_opportunity_id_is_a_scenario_error_that_does_not_echo_it() -> None:
    req = request(options=[option(), alternative(1, SENTINEL_ID)])
    with pytest.raises(ScenarioError) as raised:
        analyze(req)
    err = raised.value
    assert (err.code, err.field) == ("unknown_opportunity", "options.1.opportunity_id")
    assert SENTINEL_ID not in err.message and SENTINEL_ID not in str(err)


def test_unknown_ids_are_rejected_even_when_there_is_no_coverage() -> None:
    req = noida_request(options=noida_request().options[:1] + [alternative(1, SENTINEL_ID)])
    with pytest.raises(ScenarioError) as raised:
        analyze(req)
    assert raised.value.code == "unknown_opportunity"


def test_unknown_id_on_the_original_is_also_rejected() -> None:
    req = request(options=[option(opportunity_id=SENTINEL_ID), alternative()])
    with pytest.raises(ScenarioError) as raised:
        analyze(req)
    assert raised.value.field == "options.0.opportunity_id"


def test_an_alternative_with_no_market_evidence_is_analysed_in_a_covered_market() -> None:
    req = request(options=[option(), alternative(1, link=None)])
    result = analyze(req)
    assert [o.option_id for o in result.options] == ["original-cakes", "alt-1"]
    alt = next(o for o in result.options if o.option_id == "alt-1")
    assert alt.opportunity_id is None
    market = next(s for s in alt.score.scores if s.dimension == "market_signal")
    assert market.score == 50 and "no market evidence" in market.reason
    assert result.skipped_option_ids == []


def test_an_alternative_without_a_link_is_simply_skipped_when_there_is_no_coverage() -> None:
    req = noida_request(options=noida_request().options[:1] + [alternative(1, link=None)])
    assert analyze(req).skipped_option_ids == ["alt-1"]


def test_scenario_error_messages_are_fixed_text() -> None:
    for code in ("unknown_opportunity",):
        err = ScenarioError(code, "options.0.opportunity_id")
        assert err.message and "options" not in err.message


# ---- purity -----------------------------------------------------------------------------------


def test_analysis_does_not_mutate_the_request_or_the_dataset() -> None:
    req = request()
    before_req = req.model_dump_json()
    data = dataset()
    before_ids = data.ids()
    AnalyzeService(data, FakeClock()).analyze(req)
    assert req.model_dump_json() == before_req
    assert data.ids() == before_ids
