"""Caveats are written for the business owner: no code field names in anything shown."""

import re
from decimal import Decimal
from typing import Any

import pytest

from app.engine.feasibility import Sourced
from app.services.compare_strategies import _caveats, compare_strategies, feasibility_for
from app.services.strategy_models import RankedStrategies
from tests.explain_helpers import IDS, analysis_for
from tests.pune_fixtures import TODAY, assumed, opportunity, option, profile

D = Decimal
SNAKE = re.compile(r"\b[a-z]+(?:_[a-z]+)+\b")  # hours_per_week, working_capital, ...


def run(opp: Any = None, opt: Any = None, prof: Any = None) -> RankedStrategies:
    alt = opt or option(id="alt", is_original=False, opportunity_id="TEST-FAKE-001")
    original = option(price=D("400"))
    return compare_strategies(prof or profile(), [original, alt], [opp or opportunity()], TODAY)


def messages(result: RankedStrategies, kind: str) -> list[str]:
    return [c.message for c in result.caveats if c.kind == kind]


def solo(prof: Any = None, opt: Any = None) -> RankedStrategies:
    """One option only, so no caveat needs to name an option: these tests are about the wording."""
    return compare_strategies(prof or profile(), [opt or option()], [], TODAY)


def test_an_assumed_weekly_hours_figure_reads_in_plain_words() -> None:
    result = solo(prof=profile(hours_per_week=assumed(12)))
    assert "Weekly hours available (12) is assumed, not provided by you" in messages(
        result, "assumption"
    )


def test_an_assumed_time_per_item_reads_in_plain_words() -> None:
    result = solo(opt=option(minutes_per_unit=assumed(100)))
    assert "Time per item (100 minutes) is assumed, not provided by you" in messages(
        result, "assumption"
    )


def test_the_field_names_stay_in_items_for_the_api() -> None:
    result = solo(prof=profile(hours_per_week=assumed(12)))
    items = {
        tuple(c.items) for c in result.caveats if c.kind in ("assumption", "engine_assumption")
    }
    assert ("hours_per_week",) in items
    assert ("working_capital",) in items and ("demand_factors",) in items


def test_the_working_capital_caveat_is_plain() -> None:
    [message] = [
        m for m in messages(solo(), "engine_assumption") if m.startswith("Working capital")
    ]
    assert re.fullmatch(
        r"Working capital reserve \(₹[\d,.]+\) is assumed: the first week's running costs "
        r"at full capacity\.",
        message,
    )


def test_the_demand_caveat_is_plain() -> None:
    assert (
        "Demand is assumed: we modelled selling 25%, 50% and 100% of your weekly capacity."
        in messages(run(), "engine_assumption")
    )


def test_missing_skills_and_equipment_are_plain() -> None:
    needy = option(id="alt", is_original=False, required_skills=["piping"],
                   required_equipment=["deck oven"])  # fmt: skip
    prof = profile(skills=["baking"], equipment=["oven"])
    caveats = _caveats(prof, needy, feasibility_for(prof, needy), None)
    by_kind = {c.kind: c for c in caveats}
    assert by_kind["missing_skills"].message == (
        "Skills this option needs that you haven't listed: piping."
    )
    assert by_kind["missing_equipment"].message == (
        "Equipment this option needs that you haven't listed: deck oven."
    )
    assert by_kind["missing_skills"].items == ["piping"]


def test_the_original_idea_with_no_evidence_has_a_plain_caveat() -> None:
    original = option(price=D("1500"), variable_cost_per_unit=D("100"))
    result = compare_strategies(profile(), [original], [], TODAY)
    assert result.recommended_id == "orig"
    assert messages(result, "no_market_evidence") == [
        "There is no market evidence for your original idea, so its market score is a neutral "
        "50, not a finding."
    ]


@pytest.mark.parametrize(
    ("status", "words"),
    [
        ("single_source", "rests on a single source"),
        ("unverified_sample", "has not been checked yet"),
    ],
)
def test_weak_verification_is_explained_in_plain_words(status: str, words: str) -> None:
    weak = opportunity(verification_status=status, verified_by=None, verified_on=None)
    [message] = messages(run(opp=weak), "verification")
    assert (
        message == f"Market evidence from test_fixture {words}, so treat its signal with caution."
    )


def test_against_evidence_caveat_is_plain() -> None:
    against = opportunity(direction="against")
    assert messages(run(opp=against), "evidence_against") == [
        "Market evidence from test_fixture argues against this option."
    ]


@pytest.mark.parametrize("scenario", IDS)
def test_no_text_shown_to_the_owner_contains_a_code_field_name(scenario: str) -> None:
    analysis = analysis_for(scenario)
    texts = [c.message for c in analysis.ranking.caveats]
    texts += [analysis.market_message, *(s.title for s in analysis.steps)]
    for score in analysis.ranking.ranked:
        texts += [score.title, *score.viability_issues, *(s.reason for s in score.scores)]
    for text in texts:
        assert not SNAKE.search(text), text


def test_the_assumption_wording_only_appears_for_assumed_inputs() -> None:
    user = Sourced[int](value=12, source="user_provided")
    result = run(prof=profile(hours_per_week=user))
    assert not any("Weekly hours" in m for m in messages(result, "assumption"))


# ---- with several options, assumed-input caveats name the option they belong to ---------------


def stall(**overrides: Any) -> Any:
    return option(id="alt", title="Weekend stall", is_original=False,
                  opportunity_id="TEST-FAKE-001", **overrides)  # fmt: skip


def multi() -> RankedStrategies:
    result = run(prof=profile(hours_per_week=assumed(12)), opt=stall(minutes_per_unit=assumed(100)))
    assert result.recommended_id == "alt"  # the stall, so its title is the one that must appear
    return result


def test_with_several_options_hours_minutes_and_working_capital_name_the_option() -> None:
    result = multi()
    assert messages(result, "assumption") == [
        "Weekend stall: weekly hours available (12) is assumed, not provided by you",
        "Weekend stall: time per item (100 minutes) is assumed, not provided by you",
    ]
    capital = [m for m in messages(result, "engine_assumption") if "orking capital" in m]
    assert len(capital) == 1 and capital[0].startswith("Weekend stall: working capital reserve (₹")


def test_the_field_names_in_items_are_unchanged_by_the_prefix() -> None:
    items = {
        tuple(c.items) for c in multi().caveats if c.kind in ("assumption", "engine_assumption")
    }
    assert {("hours_per_week",), ("minutes_per_unit",), ("working_capital",)} <= items


def test_caveats_that_are_not_about_assumed_inputs_are_not_prefixed() -> None:
    result = multi()
    demand = [m for m in messages(result, "engine_assumption") if m.startswith("Demand")]
    assert demand == [
        "Demand is assumed: we modelled selling 25%, 50% and 100% of your weekly capacity."
    ]
    for caveat in result.caveats:
        if caveat.kind not in ("assumption",) and "working_capital" not in caveat.items:
            assert not caveat.message.startswith("Weekend stall:"), caveat.message


def test_with_a_single_option_the_caveats_are_not_prefixed() -> None:
    lone = option(minutes_per_unit=assumed(90))
    result = compare_strategies(profile(hours_per_week=assumed(12)), [lone], [], TODAY)
    assert messages(result, "assumption") == [
        "Weekly hours available (12) is assumed, not provided by you",
        "Time per item (90 minutes) is assumed, not provided by you",
    ]
    assert any(
        m.startswith("Working capital reserve (") for m in messages(result, "engine_assumption")
    )


def test_the_nothing_viable_case_is_unchanged_hours_once_and_the_rest_per_option() -> None:
    # Different running costs, so the working capital differs and is named per option.
    over = [
        option(fixed_startup_costs=D("9000")),
        stall(fixed_startup_costs=D("9000"), variable_cost_per_unit=D("400")),
    ]
    result = compare_strategies(profile(hours_per_week=assumed(12)), over, [opportunity()], TODAY)
    assert result.recommended_id is None
    texts = [c.message for c in result.caveats]
    assert texts.count("Weekly hours available (12) is assumed, not provided by you") == 1
    assert any(t.startswith("Weekend stall: working capital reserve") for t in texts)


def test_a_suggestion_in_the_result_counts_as_another_option() -> None:
    from tests.test_suggestions import analyze, sample

    texts = [c.message for c in analyze(sample()).ranking.caveats]
    assert any(t.startswith("Custom celebration cakes: weekly hours available (20)") for t in texts)
    assert any(t.startswith("Custom celebration cakes: working capital reserve") for t in texts)
