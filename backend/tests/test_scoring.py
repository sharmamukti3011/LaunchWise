"""Dimension scorers. Fixtures (Pune bakery, fake opportunities) live in pune_fixtures."""

from datetime import date
from decimal import Decimal

import pytest

from app.engine.feasibility import Sourced
from app.services.scoring import (
    budget_fit,
    capacity_fit,
    margin_fit,
    market_signal_fit,
    skill_equipment_fit,
)
from tests.pune_fixtures import TODAY, assumed, feasibility, opportunity, option, profile

D = Decimal


# ---- margin fit -------------------------------------------------------------------------------


def test_margin_fit_scales_linearly_and_caps_at_50_percent() -> None:
    # 800 - 350 = 450 -> 56.25% -> capped at 100.
    assert margin_fit(feasibility()).score == 100
    # 800 - 600 = 200 -> 25% -> 50.
    assert margin_fit(feasibility(option(variable_cost_per_unit=D("600")))).score == 50


@pytest.mark.parametrize("cost", ["800", "900"])
def test_margin_fit_is_zero_for_zero_or_negative_margin(cost: str) -> None:
    assert margin_fit(feasibility(option(variable_cost_per_unit=D(cost)))).score == 0


def test_margin_fit_is_zero_when_there_is_no_price() -> None:
    score = margin_fit(feasibility(option(price=D("0"), variable_cost_per_unit=D("0"))))
    assert score.score == 0
    assert "no price" in score.reason


def test_margin_reason_shows_pct_and_weekly_contribution_at_medium_demand() -> None:
    reason = margin_fit(feasibility()).reason
    assert "56.25%" in reason
    # 450 per unit x 3 units a week (50% of 6 capacity) = 1,350.
    assert "₹1,350.00" in reason
    assert "medium demand" in reason
    assert "assum" in reason  # the 50% demand factor is labelled an assumption


def test_weekly_contribution_does_not_change_the_score() -> None:
    low_capacity = profile(units_per_day=1)
    assert margin_fit(feasibility(prof=low_capacity)).score == margin_fit(feasibility()).score


# ---- budget fit -------------------------------------------------------------------------------


def test_budget_fit_within_budget_scales_with_headroom() -> None:
    # 6,000 startup + 2,100 working capital (350 x 6) = 8,100; headroom 1,900 = 19% -> 50 + 19.
    score = budget_fit(feasibility())
    assert score.score == 69
    assert "₹8,100.00" in score.reason and "₹10,000.00" in score.reason
    assert "working capital" in score.reason


def test_budget_fit_exact_fit_scores_50() -> None:
    assert budget_fit(feasibility(option(fixed_startup_costs=D("7900")))).score == 50


def test_budget_fit_caps_at_100_with_large_headroom() -> None:
    assert budget_fit(feasibility(option(fixed_startup_costs=D("1000")))).score == 100


def test_budget_fit_is_zero_when_working_capital_tips_over_budget() -> None:
    # Startup alone (8,000) fits, but 8,000 + 2,100 > 10,000.
    score = budget_fit(feasibility(option(fixed_startup_costs=D("8000"))))
    assert score.score == 0
    assert "₹100.00" in score.reason  # shortfall
    assert "over budget" in score.reason


def test_budget_fit_handles_zero_budget() -> None:
    score = budget_fit(feasibility(prof=profile(budget=D("0"))))
    assert score.score == 0


# ---- capacity fit -----------------------------------------------------------------------------


def test_capacity_fit_full_when_hours_suffice() -> None:
    # 90 min x 6 units = 9 h needed, 12 h available.
    score = capacity_fit(profile(), option(), feasibility())
    assert score.score == 100
    assert "9.0" in score.reason and "12" in score.reason


def test_capacity_reason_tags_hours_as_assumptions() -> None:
    reason = capacity_fit(profile(), option(), feasibility()).reason
    assert reason.count("assumption") == 2  # minutes_per_unit and hours_per_week


def test_capacity_reason_tags_user_provided_hours() -> None:
    user_hours = Sourced[int](value=12, source="user_provided")
    reason = capacity_fit(profile(hours_per_week=user_hours), option(), feasibility()).reason
    assert "user provided" in reason


def test_capacity_fit_falls_off_when_hours_fall_short() -> None:
    # 200 min x 6 = 20 h needed vs 12 h available -> 60.
    slow = option(minutes_per_unit=assumed(200))
    assert capacity_fit(profile(), slow, feasibility(slow)).score == 60


def test_capacity_fit_is_zero_without_weekly_capacity() -> None:
    p = profile(days_per_week=0)
    score = capacity_fit(p, option(), feasibility(prof=p))
    assert score.score == 0
    assert "no weekly capacity" in score.reason


def test_capacity_fit_is_zero_without_hours_available() -> None:
    p = profile(hours_per_week=assumed(0))
    assert capacity_fit(p, option(), feasibility(prof=p)).score == 0


def test_capacity_fit_full_when_option_needs_no_time() -> None:
    quick = option(minutes_per_unit=assumed(0))
    p = profile(hours_per_week=assumed(0))
    assert capacity_fit(p, quick, feasibility(quick, p)).score == 100


# ---- skill and equipment fit ------------------------------------------------------------------


def test_skill_equipment_fit_full_when_nothing_required() -> None:
    score = skill_equipment_fit(profile(), option())
    assert score.score == 100
    assert "nothing required" in score.reason


def test_skill_equipment_fit_full_when_all_present() -> None:
    opt = option(required_skills=["baking"], required_equipment=["oven"])
    assert skill_equipment_fit(profile(), opt).score == 100


def test_skill_equipment_fit_names_missing_items() -> None:
    opt = option(
        required_skills=["baking", "piping", "food photography"],
        required_equipment=["oven", "walk-in freezer"],
    )
    score = skill_equipment_fit(profile(), opt)
    assert score.score == 40  # 2 of 5 present
    assert "missing skills: piping, food photography" in score.reason
    assert "missing equipment: walk-in freezer" in score.reason


def test_skill_equipment_fit_names_only_the_missing_kind() -> None:
    opt = option(required_skills=["baking"], required_equipment=["pizza oven"])
    reason = skill_equipment_fit(profile(), opt).reason
    assert "missing equipment: pizza oven" in reason
    assert "missing skills" not in reason


def test_skill_equipment_fit_ignores_case_and_spacing_and_duplicates() -> None:
    opt = option(required_skills=[" Baking ", "baking"], required_equipment=["OVEN"])
    assert skill_equipment_fit(profile(), opt).score == 100


def test_skill_equipment_fit_is_zero_when_nothing_matches() -> None:
    opt = option(required_skills=["welding"], required_equipment=["forge"])
    assert skill_equipment_fit(profile(), opt).score == 0


# ---- market signal ----------------------------------------------------------------------------


def test_original_without_evidence_gets_neutral_50() -> None:
    score = market_signal_fit(option(), None, TODAY)
    assert score.score == 50
    assert "no market evidence" in score.reason


def test_alternative_without_linked_opportunity_scores_zero() -> None:
    score = market_signal_fit(option(id="alt", is_original=False), None, TODAY)
    assert score.score == 0
    assert "no linked" in score.reason


@pytest.mark.parametrize(("strength", "expected"), [("low", 30), ("medium", 60), ("high", 90)])
def test_market_signal_follows_signal_strength_when_verified(strength: str, expected: int) -> None:
    opt = option(id="alt", is_original=False, opportunity_id="TEST-FAKE-001")
    score = market_signal_fit(opt, opportunity(signal_strength=strength), TODAY)
    assert score.score == expected
    assert "TEST-FAKE-001" in score.reason and strength in score.reason


@pytest.mark.parametrize("status", ["single_source", "unverified_sample"])
def test_unverified_status_takes_a_fixed_deduction(status: str) -> None:
    opt = option(id="alt", is_original=False, opportunity_id="TEST-FAKE-001")
    score = market_signal_fit(opt, opportunity(verification_status=status), TODAY)
    assert score.score == 75  # 90 - 15
    assert status.replace("_", " ") in score.reason


def test_future_dated_opportunity_is_scored() -> None:
    opt = option(id="alt", is_original=False, opportunity_id="TEST-FAKE-001")
    assert market_signal_fit(opt, opportunity(event_date=date(2026, 11, 18)), TODAY).score == 90


def test_event_today_has_not_passed() -> None:
    opt = option(id="alt", is_original=False, opportunity_id="TEST-FAKE-001")
    assert market_signal_fit(opt, opportunity(event_date=TODAY), TODAY).score == 90


def test_past_dated_opportunity_scores_zero_with_event_passed() -> None:
    opt = option(id="alt", is_original=False, opportunity_id="TEST-FAKE-001")
    score = market_signal_fit(opt, opportunity(event_date=date(2026, 11, 16)), TODAY)
    assert score.score == 0
    assert "event passed" in score.reason


def test_evergreen_opportunity_never_expires() -> None:
    opt = option(id="alt", is_original=False, opportunity_id="TEST-FAKE-001")
    ever = opportunity(is_evergreen=True, event_date=None)
    score = market_signal_fit(opt, ever, date(2099, 1, 1))
    assert score.score == 90
    assert "evergreen" in score.reason


def test_evergreen_with_old_event_date_still_never_expires() -> None:
    opt = option(id="alt", is_original=False, opportunity_id="TEST-FAKE-001")
    ever = opportunity(is_evergreen=True, event_date=date(2020, 1, 1))
    assert market_signal_fit(opt, ever, TODAY).score == 90


def test_original_linked_to_an_opportunity_uses_it() -> None:
    opt = option(opportunity_id="TEST-FAKE-001")
    assert market_signal_fit(opt, opportunity(signal_strength="low"), TODAY).score == 30
