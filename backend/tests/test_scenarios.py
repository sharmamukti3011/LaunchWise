"""The four saved scenarios, run against the SHIPPED dataset, with hand-checkable scores.

Each expected score below can be worked out from the rules in `app/services/scoring.py`. The
arithmetic is written next to the assertions so you can verify it with a pencil.
Weights: margin 30, budget 20, capacity 20, skill/equipment 15, market signal 15.
Every shipped dataset entry is still `unverified_sample`, so a linked option's market score is
its signal points minus 15: low 30 - 15 = 15, medium 60 - 15 = 45. The links used here are PUNE-001
(medium), PUNE-002 and PUNE-003 (both low). An original idea with no evidence gets a neutral 50.
"""

import json
from decimal import Decimal
from typing import Any

import pytest

from app.services.analyze_models import AnalyzeRequest, AnalyzeResponse
from app.services.analyze_service import AnalyzeService
from app.services.demo_catalog import DEMO_DIR
from app.services.market_data import load_dataset
from tests.fakes import FakeClock

D = Decimal
SCENARIOS = DEMO_DIR  # the shipped demo files are the only copy of these scenarios
NAMES = [
    "a_alternative_beats_thin_margin_original",
    "b_strong_original_wins",
    "c_no_viable_option",
    "d_noida_feasibility_only",
]


def load(name: str) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((SCENARIOS / f"{name}.json").read_text())
    return data


def run(name: str, body: dict[str, Any] | None = None) -> AnalyzeResponse:
    request = AnalyzeRequest.model_validate(body or load(name))
    return AnalyzeService(load_dataset(), FakeClock()).analyze(request)


def scores(result: AnalyzeResponse, option_id: str) -> dict[str, int]:
    ranked = next(s for s in result.ranking.ranked if s.option_id == option_id)
    return {s.dimension: s.score for s in ranked.scores}


def total(result: AnalyzeResponse, option_id: str) -> Decimal:
    return next(s.total for s in result.ranking.ranked if s.option_id == option_id)


@pytest.mark.parametrize("name", NAMES)
def test_every_fixture_is_a_valid_request(name: str) -> None:
    AnalyzeRequest.model_validate(load(name))


def test_fixture_links_point_at_real_shipped_dataset_ids() -> None:
    shipped = load_dataset().ids()
    for name in NAMES:
        for option in load(name)["options"]:
            link = option.get("opportunity_id")
            assert link is None or link in shipped, f"{name}: {link}"


# ---- (a) an alternative beats a thin-margin original ------------------------------------------


def test_a_the_alternative_beats_the_thin_margin_original() -> None:
    result = run("a_alternative_beats_thin_margin_original")
    assert result.market_coverage == "covered"
    assert [s.option_id for s in result.ranking.ranked] == [
        "custom-celebration-cakes",
        "original-cakes",
        "small-shop",
    ]
    assert result.ranking.recommended_id == "custom-celebration-cakes"
    assert result.ranking.keep_original is False


def test_a_scores_by_dimension() -> None:
    result = run("a_alternative_beats_thin_margin_original")
    # Original: price 500, cost 450 -> margin 50 = 10% -> 10/50*100 = 20.
    #   budget: 3000 + 450*6 (working capital) = 5700; headroom 4300 = 43% -> 50 + 43 = 93.
    #   capacity: 60 min * 6 units = 6 h <= 12 h -> 100. skills/equipment all present -> 100.
    #   market: no evidence for the original -> 50.
    #   total = (20*30 + 93*20 + 100*20 + 100*15 + 50*15) / 100 = 67.10
    assert scores(result, "original-cakes") == {
        "margin": 20, "budget": 93, "capacity": 100, "skill_equipment": 100, "market_signal": 50,
    }  # fmt: skip
    assert total(result, "original-cakes") == D("67.10")
    # Custom cakes: price 1400, cost 500 -> margin 900 = 64.29% -> capped at 100.
    #   budget: 4000 + 500*6 = 7000; headroom 3000 = 30% -> 80.
    #   capacity: 100 min * 6 = 10 h <= 12 h -> 100. skills/equipment present -> 100.
    #   market: PUNE-001 is a medium signal, 60, minus 15 for unverified -> 45.
    #   total = (100*30 + 80*20 + 100*20 + 100*15 + 45*15) / 100 = 8775 / 100 = 87.75
    assert scores(result, "custom-celebration-cakes") == {
        "margin": 100, "budget": 80, "capacity": 100, "skill_equipment": 100, "market_signal": 45,
    }  # fmt: skip
    assert total(result, "custom-celebration-cakes") == D("87.75")
    # Small shop: margin 600/900 = 66.67% -> 100. budget: 150000 + 300*6 is far over 10000 -> 0.
    #   capacity 90 min * 6 = 9 h -> 100.
    #   equipment: 1 of 3 required items missing -> floor(2/3*100) = 66.
    #   market: PUNE-003 is a low signal, 30, minus 15 -> 15.
    #   total = (100*30 + 0 + 100*20 + 66*15 + 15*15) / 100 = 62.15, but not viable.
    assert scores(result, "small-shop") == {
        "margin": 100, "budget": 0, "capacity": 100, "skill_equipment": 66, "market_signal": 15,
    }  # fmt: skip
    assert total(result, "small-shop") == D("62.15")
    shop = next(s for s in result.ranking.ranked if s.option_id == "small-shop")
    assert not shop.viable and "over budget" in shop.viability_issues


def test_a_caveats_describe_the_recommended_option_only() -> None:
    kinds = [c.kind for c in run("a_alternative_beats_thin_margin_original").ranking.caveats]
    assert "verification" in kinds  # the linked evidence is an unverified placeholder
    assert "assumption" in kinds and "engine_assumption" in kinds
    assert "missing_equipment" not in kinds


# ---- (b) a strong original wins; the alternative needs equipment the owner lacks --------------


def test_b_the_original_wins_because_the_alternative_lacks_equipment() -> None:
    result = run("b_strong_original_wins")
    assert [s.option_id for s in result.ranking.ranked] == [
        "original-cakes",
        "sourdough-subscription",
    ]
    assert result.ranking.recommended_id == "original-cakes"
    assert result.ranking.keep_original is True


def test_b_scores_by_dimension() -> None:
    result = run("b_strong_original_wins")
    # Original: price 750, cost 450 -> margin 300 = 40% -> 40/50*100 = 80.
    #   budget: 3000 + 450*6 = 5700; headroom 4300 = 43% -> 93. capacity 6 h -> 100. skills -> 100.
    #   market 50. total = (80*30 + 93*20 + 100*20 + 100*15 + 50*15) / 100 = 85.10
    assert scores(result, "original-cakes") == {
        "margin": 80, "budget": 93, "capacity": 100, "skill_equipment": 100, "market_signal": 50,
    }  # fmt: skip
    assert total(result, "original-cakes") == D("85.10")
    # Sourdough: price 300, cost 80 -> margin 220 = 73.33% -> 100.
    #   budget: 2000 + 80*6 = 2480; headroom 7520 = 75.2% -> 50 + 75 = 125 -> capped at 100.
    #   capacity: 60 min * 6 = 6 h -> 100.
    #   equipment: needs baking + deck oven + proofing basket; owner lacks 2 of 3
    #   -> floor(1/3*100) = 33.
    #   market: PUNE-002 is a low signal, 30, minus 15 -> 15.
    #   total = (100*30 + 100*20 + 100*20 + 33*15 + 15*15) / 100 = 77.20
    assert scores(result, "sourdough-subscription") == {
        "margin": 100, "budget": 100, "capacity": 100, "skill_equipment": 33, "market_signal": 15,
    }  # fmt: skip
    assert total(result, "sourdough-subscription") == D("77.20")


def test_b_the_missing_equipment_is_what_decides_it() -> None:
    # Counterfactual: give the owner the two missing items. The same alternative now scores
    # (100*30 + 100*20 + 100*20 + 100*15 + 15*15) / 100 = 87.25, beating the original's 85.10.
    body = load("b_strong_original_wins")
    body["profile"]["equipment"] = ["oven", "mixer", "deck oven", "proofing basket"]
    result = run("b_strong_original_wins", body)
    assert total(result, "sourdough-subscription") == D("87.25")
    assert result.ranking.recommended_id == "sourdough-subscription"


def test_b_caveats_name_the_missing_equipment_only_when_it_is_the_recommendation() -> None:
    kinds = [c.kind for c in run("b_strong_original_wins").ranking.caveats]
    assert "no_market_evidence" in kinds  # the original idea has no dataset evidence
    assert "missing_equipment" not in kinds  # the original needs nothing the owner lacks


# ---- (c) no viable option ---------------------------------------------------------------------


def test_c_nothing_is_viable_so_nothing_is_recommended() -> None:
    result = run("c_no_viable_option")
    assert result.ranking.recommended_id is None
    assert result.ranking.keep_original is False
    assert result.ranking.caveats == []
    assert all(not s.viable for s in result.ranking.ranked)


def test_c_scores_by_dimension_and_reasons() -> None:
    result = run("c_no_viable_option")
    # The higher scorer still is not recommended: it is not viable.
    assert [s.option_id for s in result.ranking.ranked] == [
        "premium-wedding-cakes",
        "original-cakes",
    ]
    # Original: price 500, cost 520 -> margin -20 -> 0. budget: 1500 + 520*6 = 4620 of 5000;
    #   headroom 380 = 7.6% -> 50 + 7 = 57. capacity 6 h -> 100. skills -> 100. market 50.
    #   total = (0*30 + 57*20 + 100*20 + 100*15 + 50*15) / 100 = 53.90; fails: no positive margin.
    assert scores(result, "original-cakes") == {
        "margin": 0, "budget": 57, "capacity": 100, "skill_equipment": 100, "market_signal": 50,
    }  # fmt: skip
    assert total(result, "original-cakes") == D("53.90")
    original = next(s for s in result.ranking.ranked if s.option_id == "original-cakes")
    assert original.viability_issues == ["no positive margin"]
    # Premium: margin 800/1200 = 66.67% -> 100. budget: 40000 + 400*6 is far over 5000 -> 0.
    #   capacity 90 min * 6 = 9 h -> 100. equipment: walk-in fridge missing, 1 of 2 -> 50.
    #   market: PUNE-001 is a medium signal, 60, minus 15 -> 45.
    #   total = (100*30 + 0 + 100*20 + 50*15 + 45*15) / 100 = 6425 / 100 = 64.25; not viable.
    assert scores(result, "premium-wedding-cakes") == {
        "margin": 100, "budget": 0, "capacity": 100, "skill_equipment": 50, "market_signal": 45,
    }  # fmt: skip
    assert total(result, "premium-wedding-cakes") == D("64.25")
    premium = next(s for s in result.ranking.ranked if s.option_id == "premium-wedding-cakes")
    assert premium.viability_issues == ["over budget"]


# ---- (d) Noida: feasibility only --------------------------------------------------------------


def test_d_noida_high_protein_breakfast_is_feasibility_only() -> None:
    result = run("d_noida_feasibility_only")
    assert result.market_coverage == "none"
    assert result.market_message and "feasibility-only" in result.market_message
    assert [o.option_id for o in result.options] == ["protein-breakfast-box"]
    assert result.skipped_option_ids == ["pune-cake-pivot"]  # linked to Pune, never compared
    assert result.evidence == []
    assert result.ranking.recommended_id == "protein-breakfast-box"
    assert result.ranking.keep_original is True  # no pivot
    assert [s.option_id for s in result.ranking.ranked] == ["protein-breakfast-box"]


def test_d_numbers_and_scores() -> None:
    result = run("d_noida_feasibility_only")
    numbers = result.options[0].feasibility
    # 40 boxes/day * 6 days = 240 a week; margin 150 - 80 = 70.00 (46.67%).
    assert numbers.weekly_capacity.value == 240
    assert numbers.contribution_margin.value == D("70.00")
    assert numbers.budget_check.working_capital is not None
    assert numbers.budget_check.working_capital.value == D("19200.00")  # 80 * 240
    # margin: 46.67/50*100 = 93.
    # budget: 15000 + 19200 = 34200 of 50000; headroom 15800 = 31.6% -> 81.
    # capacity: 8 min * 240 = 32 h <= 40 h -> 100. skills -> 100. market: no evidence -> 50.
    # total = (93*30 + 81*20 + 100*20 + 100*15 + 50*15) / 100 = 86.60
    assert scores(result, "protein-breakfast-box") == {
        "margin": 93, "budget": 81, "capacity": 100, "skill_equipment": 100, "market_signal": 50,
    }  # fmt: skip
    assert total(result, "protein-breakfast-box") == D("86.60")
    signal = next(s for s in result.options[0].score.scores if s.dimension == "market_signal")
    assert "no market evidence" in signal.reason


def test_d_makes_no_market_claims_that_are_not_in_the_dataset() -> None:
    result = run("d_noida_feasibility_only")
    text = result.model_dump_json().lower()
    assert "pune" not in text.replace("pune-cake-pivot", "")  # no Pune evidence leaks into Noida
    assert "todo-verify" not in text
    assert not any(c.kind == "verification" for c in result.ranking.caveats)
