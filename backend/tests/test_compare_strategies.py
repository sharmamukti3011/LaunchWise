"""compare_strategies: ranking, viability and the Pune scenarios.

Pune home bakery: Rs 10,000, 3 cakes/day, weekends only. Fixtures are in pune_fixtures.
"""

from datetime import date
from decimal import Decimal

import pytest

from app.engine.feasibility import Sourced
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
    # New rule: skill and equipment fit of 0 makes the stall non-viable (it was viable before).
    scored_stall = by_id(result, "stall")
    assert scored_stall.viable is False
    assert any(
        "skill and equipment fit is 0" in issue and "missing equipment: stall tent" in issue
        for issue in scored_stall.viability_issues
    )


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


# ---- hard gates: zero skill/equipment fit and zero capacity fit -------------------------------


def no_skills_stall(**overrides: object) -> StrategyOption:
    data: dict[str, object] = {
        "required_skills": ["customer service"],
        "required_equipment": ["stall tent"],
    }
    data.update(overrides)
    return market_stall(**data)


def test_zero_skill_equipment_fit_is_non_viable_and_names_the_missing_items() -> None:
    scored = by_id(run([option(), no_skills_stall()]), "stall")
    assert scored.viable is False
    (issue,) = scored.viability_issues
    assert issue.startswith("skill and equipment fit is 0")
    assert "missing skills: customer service" in issue
    assert "missing equipment: stall tent" in issue


def test_partial_skill_equipment_match_stays_viable() -> None:
    assert by_id(run([thin_original(), market_stall()]), "stall").viable is True  # fit 66


def test_zero_skill_fit_option_loses_even_with_a_higher_total() -> None:
    result = run([thin_original(), no_skills_stall()])
    assert by_id(result, "stall").total > by_id(result, "orig").total
    assert result.recommended_id == "orig"
    assert [s.option_id for s in result.ranked] == ["orig", "stall"]


def test_only_option_with_zero_skill_fit_gives_no_recommendation() -> None:
    result = run([option(required_skills=["welding"])])
    assert result.recommended_id is None
    assert result.keep_original is False


def test_zero_capacity_fit_from_no_weekly_capacity_is_non_viable() -> None:
    weekend_less = profile(days_per_week=0)
    scored = by_id(compare_strategies(weekend_less, [option()], [opportunity()], TODAY), "orig")
    assert scored.viable is False
    assert any(
        i.startswith("capacity fit is 0") and "no weekly capacity" in i
        for i in scored.viability_issues
    )


def test_zero_capacity_fit_from_no_hours_available_is_non_viable() -> None:
    no_hours = profile(hours_per_week=assumed(0))
    scored = by_id(compare_strategies(no_hours, [option()], [opportunity()], TODAY), "orig")
    assert scored.viable is False
    assert any(i.startswith("capacity fit is 0") for i in scored.viability_issues)


def test_low_but_non_zero_capacity_fit_stays_viable() -> None:
    slow = option(minutes_per_unit=assumed(200))  # 20 h needed vs 12 available -> 60
    assert by_id(run([slow]), "orig").viable is True


def test_several_gates_are_all_reported() -> None:
    bad = option(fixed_startup_costs=D("9000"), required_skills=["welding"])
    issues = by_id(run([bad]), "orig").viability_issues
    assert len(issues) == 2
    assert issues[0] == "over budget"
    assert issues[1].startswith("skill and equipment fit is 0")


# ---- caveats on the recommended option --------------------------------------------------------


def kinds(result: RankedStrategies) -> list[str]:
    return [c.kind for c in result.caveats]


def test_caveats_name_missing_skills_and_equipment_separately() -> None:
    stall = market_stall(
        required_skills=["baking", "piping"], required_equipment=["oven", "stall tent", "gas stove"]
    )
    result = run([thin_original(), stall])
    assert result.recommended_id == "stall"
    by_kind = {c.kind: c for c in result.caveats}
    assert by_kind["missing_skills"].items == ["piping"]
    assert by_kind["missing_equipment"].items == ["stall tent", "gas stove"]
    assert "piping" in by_kind["missing_skills"].message
    assert "stall tent, gas stove" in by_kind["missing_equipment"].message


def test_caveats_list_assumption_tagged_inputs_used() -> None:
    result = run([thin_original(), market_stall()])  # fixtures tag hours and minutes as assumptions
    assumptions = [c for c in result.caveats if c.kind == "assumption"]
    assert sorted(c.items[0] for c in assumptions) == ["hours_per_week", "minutes_per_unit"]
    assert all("assumption" in c.message for c in assumptions)
    assert any("12" in c.message for c in assumptions)  # the value used
    assert any("90" in c.message for c in assumptions)


def test_user_provided_inputs_are_not_caveated_as_assumptions() -> None:
    user = Sourced[int](value=12, source="user_provided")
    mins = Sourced[int](value=90, source="user_provided")
    result = compare_strategies(
        profile(hours_per_week=user), [option(minutes_per_unit=mins)], [opportunity()], TODAY
    )
    assert result.recommended_id == "orig"
    assert result.caveats == []


def test_only_the_assumption_actually_used_is_listed() -> None:
    user_hours = Sourced[int](value=12, source="user_provided")
    result = compare_strategies(
        profile(hours_per_week=user_hours), [option()], [opportunity()], TODAY
    )
    assert [c.items for c in result.caveats if c.kind == "assumption"] == [["minutes_per_unit"]]


@pytest.mark.parametrize("status", ["single_source", "unverified_sample"])
def test_caveat_for_verification_below_verified(status: str) -> None:
    opp = opportunity(verification_status=status, verified_by=None, verified_on=None)
    result = run([thin_original(), market_stall(required_equipment=["oven"])], [opp])
    assert result.recommended_id == "stall"
    (caveat,) = [c for c in result.caveats if c.kind == "verification"]
    assert OPP_ID in caveat.message
    assert status.replace("_", " ") in caveat.message
    assert caveat.items == [OPP_ID]


def test_no_verification_caveat_for_verified_opportunity() -> None:
    result = run([thin_original(), market_stall()])
    assert "verification" not in kinds(result)


def test_caveats_only_describe_the_recommended_option() -> None:
    # The original (not recommended) lacks welding; the recommended stall has no gaps.
    result = run(
        [
            thin_original().model_copy(update={"required_skills": ["welding"]}),
            market_stall(required_equipment=["oven"]),
        ]
    )
    assert result.recommended_id == "stall"
    assert "missing_skills" not in kinds(result)
    assert not any("welding" in c.message for c in result.caveats)


def test_caveats_empty_when_nothing_is_recommended() -> None:
    result = run([option(fixed_startup_costs=D("9000"))])
    assert result.recommended_id is None
    assert result.caveats == []


def test_caveat_order_is_missing_then_assumptions_then_verification() -> None:
    opp = opportunity(verification_status="single_source", verified_by=None, verified_on=None)
    result = run([thin_original(), market_stall()], [opp])
    assert kinds(result) == [
        "missing_equipment",
        "assumption",
        "assumption",
        "verification",
    ]
