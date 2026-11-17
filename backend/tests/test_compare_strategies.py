"""compare_strategies: ranking, viability and the Pune scenarios.

Pune home bakery: Rs 10,000, 3 cakes/day, weekends only. Fixtures are in pune_fixtures.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.services.compare_strategies import WEIGHTS, StrategyComparisonError, compare_strategies
from app.services.strategy_models import Opportunity, OptionScore, RankedStrategies, StrategyOption
from tests.pune_fixtures import TODAY, assumed, opportunity, option, profile

D = Decimal
OPP_ID = "TEST-FAKE-001"


def thin_original() -> StrategyOption:
    # 600 - 500 = 100 margin (16.67%): fits the budget but earns little.
    return option(price=D("600"), variable_cost_per_unit=D("500"), fixed_startup_costs=D("5000"))


def market_stall(**overrides: object) -> StrategyOption:
    data: dict[str, object] = {
        "id": "stall",
        "title": "Weekend market stall",
        "is_original": False,
        "price": D("900"),
        "variable_cost_per_unit": D("400"),
        "fixed_startup_costs": D("3000"),
        "required_skills": ["baking"],
        "required_equipment": ["oven", "stall tent"],
        "opportunity_id": OPP_ID,
    }
    data.update(overrides)
    return option(**data)


def by_id(result: RankedStrategies, option_id: str) -> OptionScore:
    return next(s for s in result.ranked if s.option_id == option_id)


def dimension(score: OptionScore, name: str) -> int:
    return next(d.score for d in score.scores if d.dimension == name)


def run(options: list[StrategyOption], opps: list[Opportunity] | None = None) -> RankedStrategies:
    return compare_strategies(profile(), options, opps or [opportunity()], TODAY)


# ---- Pune scenarios ---------------------------------------------------------------------------


def test_pune_keeping_the_original_ranks_first() -> None:
    # Good-margin original; the stall matches none of its required skills and equipment.
    stall = market_stall(required_skills=["customer service"], required_equipment=["stall tent"])
    result = run([option(), stall])

    assert [s.option_id for s in result.ranked] == ["orig", "stall"]
    assert result.recommended_id == "orig"
    assert result.keep_original is True
    assert by_id(result, "orig").total == D("86.30")  # reproducible, hand-checked
    assert by_id(result, "orig").total > by_id(result, "stall").total


def test_pune_verified_alternative_with_better_margin_ranks_first() -> None:
    result = run([thin_original(), market_stall()])

    assert [s.option_id for s in result.ranked] == ["stall", "orig"]
    assert result.recommended_id == "stall"
    assert result.keep_original is False
    stall, orig = by_id(result, "stall"), by_id(result, "orig")
    assert dimension(stall, "margin") > dimension(orig, "margin")
    assert stall.total == D("92.60")
    assert orig.total == D("66.40")


def test_pune_no_viable_option_recommends_nothing() -> None:
    over_budget = option(fixed_startup_costs=D("9000"))  # 9,000 + 2,100 working capital > 10,000
    expired = market_stall()
    past = opportunity(event_date=date(2026, 11, 1))
    result = run([over_budget, expired], [past])

    assert result.recommended_id is None
    assert result.keep_original is False
    assert [s.viable for s in result.ranked] == [False, False]
    assert "over budget" in by_id(result, "orig").viability_issues
    assert "event passed" in by_id(result, "stall").viability_issues


# ---- ranking rules ----------------------------------------------------------------------------


def test_viable_options_outrank_non_viable_even_with_a_lower_total() -> None:
    # Over-budget alternative scores high everywhere else but cannot be recommended.
    pricey = market_stall(
        price=D("1000"),
        variable_cost_per_unit=D("300"),
        fixed_startup_costs=D("9500"),
        required_skills=[],
        required_equipment=[],
    )
    result = run([thin_original(), pricey])

    assert by_id(result, "stall").total > by_id(result, "orig").total
    assert [s.option_id for s in result.ranked] == ["orig", "stall"]
    assert result.recommended_id == "orig"


def test_zero_margin_option_is_not_viable() -> None:
    flat = option(price=D("500"), variable_cost_per_unit=D("500"), fixed_startup_costs=D("1000"))
    result = run([flat])
    assert by_id(result, "orig").viability_issues == ["no positive margin"]
    assert result.recommended_id is None


def test_original_wins_an_exact_tie() -> None:
    # Alternative gives up 5 margin points (-150 weighted) and gains 10 market points (+150).
    # Same total_required (5,580 + 2,520 = 6,000 + 2,100) keeps the budget score equal.
    tied = option(
        id="alt",
        is_original=False,
        price=D("800"),
        variable_cost_per_unit=D("420"),
        fixed_startup_costs=D("5580"),
        opportunity_id=OPP_ID,
    )
    opps = [opportunity(signal_strength="medium")]
    for options in ([option(), tied], [tied, option()]):
        result = run(options, opps)
        assert by_id(result, "orig").total == by_id(result, "alt").total == D("86.30")
        assert [s.option_id for s in result.ranked] == ["orig", "alt"]


def test_remaining_ties_break_by_id_regardless_of_input_order() -> None:
    a = market_stall(id="alpha")
    b = market_stall(id="bravo")
    for options in ([option(), b, a], [a, option(), b]):
        ranked = [s.option_id for s in run(options).ranked]
        assert ranked.index("alpha") < ranked.index("bravo")


def test_result_is_deterministic() -> None:
    options = [thin_original(), market_stall()]
    assert run(options) == run(options)


def test_weights_sum_to_100() -> None:
    assert sum(WEIGHTS.values()) == 100
    assert set(WEIGHTS) == {"margin", "budget", "capacity", "skill_equipment", "market_signal"}


def test_every_dimension_has_a_reason() -> None:
    for scored in run([thin_original(), market_stall()]).ranked:
        assert [d.dimension for d in scored.scores] == list(WEIGHTS)
        assert all(d.reason for d in scored.scores)


def test_skill_reason_names_missing_items_in_the_ranking_output() -> None:
    result = run([thin_original(), market_stall()])
    reasons = {d.dimension: d.reason for d in by_id(result, "stall").scores}
    assert "missing equipment: stall tent" in reasons["skill_equipment"]


# ---- viability and the scorer agree on "event passed" -----------------------------------------


@pytest.mark.parametrize(
    ("overrides", "expect_passed"),
    [
        ({"event_date": date(2026, 11, 16)}, True),  # yesterday
        ({"event_date": TODAY}, False),  # today has not passed
        ({"event_date": date(2026, 11, 18)}, False),  # tomorrow
        ({"event_date": date(2020, 1, 1)}, True),  # long past
        ({"is_evergreen": True, "event_date": None}, False),
        ({"is_evergreen": True, "event_date": date(2020, 1, 1)}, False),
    ],
)
def test_event_passed_reason_and_viability_always_agree(
    overrides: dict[str, object], expect_passed: bool
) -> None:
    opp = opportunity(**overrides)
    stall = market_stall(required_equipment=["oven"])  # everything else is viable
    scored = by_id(run([option(), stall], [opp]), "stall")

    reason = next(d.reason for d in scored.scores if d.dimension == "market_signal")
    assert ("event passed" in reason) is opp.has_passed(TODAY) is expect_passed
    assert ("event passed" in scored.viability_issues) is expect_passed
    assert scored.viable is (not expect_passed)
    assert (dimension(scored, "market_signal") == 0) is expect_passed


# ---- input validation -------------------------------------------------------------------------


def test_raises_when_alternative_has_no_opportunity_id() -> None:
    with pytest.raises(StrategyComparisonError, match="stall.*opportunity_id"):
        run([option(), market_stall(opportunity_id=None)])


def test_raises_on_unknown_opportunity_id() -> None:
    with pytest.raises(StrategyComparisonError, match="TEST-FAKE-404"):
        run([option(), market_stall(opportunity_id="TEST-FAKE-404")])


def test_raises_on_unknown_opportunity_id_for_the_original_too() -> None:
    with pytest.raises(StrategyComparisonError, match="TEST-FAKE-404"):
        run([option(opportunity_id="TEST-FAKE-404")])


def test_original_may_omit_opportunity_id() -> None:
    assert run([option()]).recommended_id == "orig"


def test_raises_without_an_original() -> None:
    with pytest.raises(StrategyComparisonError, match="exactly one original"):
        run([market_stall()])


def test_raises_with_two_originals() -> None:
    with pytest.raises(StrategyComparisonError, match="exactly one original"):
        run([option(), option(id="second")])


def test_raises_on_duplicate_option_ids() -> None:
    with pytest.raises(StrategyComparisonError, match="duplicate option id"):
        run([option(), market_stall(), market_stall()])


def test_raises_on_duplicate_opportunity_ids() -> None:
    with pytest.raises(StrategyComparisonError, match="duplicate opportunity id"):
        run([option()], [opportunity(), opportunity()])


def test_uses_minutes_assumption_in_capacity() -> None:
    slow = option(minutes_per_unit=assumed(200))
    reasons = {d.dimension: d.reason for d in by_id(run([slow]), "orig").scores}
    assert "assumption" in reasons["capacity"]
