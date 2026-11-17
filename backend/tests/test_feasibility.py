"""Feasibility engine tests. All money is Decimal; numbers are exact and reproducible."""

from decimal import Decimal

import pytest
from pydantic import ValidationError

from app.engine.feasibility import (
    BusinessOption,
    ConstraintProfile,
    FeasibilityResult,
    run_feasibility,
)

D = Decimal


def _profile(
    budget: str = "10000", units_per_day: int = 3, days_per_week: int = 2
) -> ConstraintProfile:
    return ConstraintProfile(
        budget=D(budget), units_per_day=units_per_day, days_per_week=days_per_week
    )


def _option(price: str = "800", variable_cost: str = "350", fixed: str = "6000") -> BusinessOption:
    return BusinessOption(
        price=D(price),
        variable_cost_per_unit=D(variable_cost),
        fixed_startup_costs=D(fixed),
    )


def test_pune_bakery_scenario() -> None:
    # Home bakery, Pune: Rs 10,000 budget, 3 cakes/day, weekends only (2 days).
    result = run_feasibility(_profile(), _option())

    assert result.startup_cost == D("6000.00")
    assert result.unit_variable_cost == D("350.00")
    assert result.contribution_margin == D("450.00")
    assert result.contribution_margin_pct == D("56.25")
    assert result.weekly_capacity == 6
    assert result.max_weekly_revenue == D("4800.00")
    assert result.budget_check.within_budget is True
    assert result.budget_check.headroom == D("4000.00")
    assert result.budget_check.shortfall == D("0.00")

    # ceil(6000 / 450) = 14 units to recover startup cost.
    assert result.break_even_units == 14
    assert result.break_even.high.weekly_units == D("6")
    assert result.break_even.high.weeks == 3  # ceil(14 / 6)
    assert result.break_even.medium.weekly_units == D("3")
    assert result.break_even.medium.weeks == 5  # ceil(14 / 3)
    assert result.break_even.low.weekly_units == D("1.5")
    assert result.break_even.low.weeks == 10  # ceil(14 / 1.5)


def test_zero_margin_never_breaks_even() -> None:
    result = run_feasibility(_profile(), _option(price="350", variable_cost="350"))

    assert result.contribution_margin == D("0.00")
    assert result.contribution_margin_pct == D("0.00")
    assert result.break_even_units is None
    assert result.break_even.low.weeks is None
    assert result.break_even.medium.weeks is None
    assert result.break_even.high.weeks is None


def test_negative_margin_never_breaks_even() -> None:
    result = run_feasibility(_profile(), _option(price="300", variable_cost="350"))

    assert result.contribution_margin == D("-50.00")
    assert result.contribution_margin_pct == D("-16.67")
    assert result.break_even_units is None
    assert result.break_even.high.weeks is None
    # Capacity and revenue are still reported honestly.
    assert result.max_weekly_revenue == D("1800.00")


def test_over_budget_reports_shortfall() -> None:
    result = run_feasibility(_profile(budget="5000"), _option(fixed="6000"))

    assert result.budget_check.within_budget is False
    assert result.budget_check.headroom == D("0.00")
    assert result.budget_check.shortfall == D("1000.00")


def test_exactly_on_budget_is_within_budget() -> None:
    result = run_feasibility(_profile(budget="6000"), _option(fixed="6000"))

    assert result.budget_check.within_budget is True
    assert result.budget_check.headroom == D("0.00")
    assert result.budget_check.shortfall == D("0.00")


def test_one_unit_per_day() -> None:
    result = run_feasibility(_profile(units_per_day=1), _option())

    assert result.weekly_capacity == 2
    assert result.max_weekly_revenue == D("1600.00")
    assert result.break_even_units == 14
    assert result.break_even.high.weeks == 7  # ceil(14 / 2)
    assert result.break_even.medium.weeks == 14  # ceil(14 / 1)
    assert result.break_even.low.weeks == 28  # ceil(14 / 0.5)


def test_zero_days_available() -> None:
    result = run_feasibility(_profile(days_per_week=0), _option())

    assert result.weekly_capacity == 0
    assert result.max_weekly_revenue == D("0.00")
    # Margin is positive but nothing can be sold, so break-even is unreachable.
    assert result.contribution_margin == D("450.00")
    assert result.break_even_units == 14
    assert result.break_even.low.weeks is None
    assert result.break_even.medium.weeks is None
    assert result.break_even.high.weeks is None


def test_very_high_price_stays_exact() -> None:
    result = run_feasibility(_profile(), _option(price="99999999.99", variable_cost="350"))

    assert result.contribution_margin == D("99999649.99")
    assert result.max_weekly_revenue == D("599999999.94")
    assert result.break_even_units == 1
    assert result.break_even.high.weeks == 1
    assert result.break_even.low.weeks == 1  # ceil(1 / 1.5)


def test_zero_price_has_no_margin_percentage() -> None:
    result = run_feasibility(_profile(), _option(price="0", variable_cost="0"))

    assert result.contribution_margin_pct is None
    assert result.break_even_units is None


def test_money_rounds_half_up_to_paise() -> None:
    result = run_feasibility(_profile(), _option(price="100.005", variable_cost="0"))

    assert result.contribution_margin == D("100.01")


def test_result_money_is_decimal_not_float() -> None:
    result = run_feasibility(_profile(), _option())

    for value in (
        result.startup_cost,
        result.unit_variable_cost,
        result.contribution_margin,
        result.contribution_margin_pct,
        result.max_weekly_revenue,
        result.budget_check.headroom,
        result.budget_check.shortfall,
    ):
        assert isinstance(value, Decimal)


def test_float_money_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ConstraintProfile(budget=10000.5, units_per_day=3, days_per_week=2)
    with pytest.raises(ValidationError):
        BusinessOption(
            price=800.0,
            variable_cost_per_unit=D("350"),
            fixed_startup_costs=D("6000"),
        )


@pytest.mark.parametrize(
    "kwargs",
    [
        {"budget": D("-1")},
        {"units_per_day": -1},
        {"days_per_week": 8},
        {"days_per_week": -1},
    ],
)
def test_invalid_profile_is_rejected(kwargs: dict[str, object]) -> None:
    base: dict[str, object] = {"budget": D("10000"), "units_per_day": 3, "days_per_week": 2}
    with pytest.raises(ValidationError):
        ConstraintProfile(**{**base, **kwargs})


def test_negative_option_costs_are_rejected() -> None:
    with pytest.raises(ValidationError):
        _option(price="-1")
    with pytest.raises(ValidationError):
        _option(variable_cost="-1")
    with pytest.raises(ValidationError):
        _option(fixed="-1")


def test_deterministic_and_what_if_reuses_same_function() -> None:
    profile, option = _profile(), _option()
    first = run_feasibility(profile, option)
    assert run_feasibility(profile, option) == first

    # What-If: raising the price changes margin and shortens break-even.
    what_if: FeasibilityResult = run_feasibility(profile, _option(price="1000"))
    assert what_if.contribution_margin == D("650.00")
    assert what_if.break_even_units == 10  # ceil(6000 / 650)
    assert what_if.break_even.medium.weeks == 4  # ceil(10 / 3)
    assert what_if.break_even.medium.weeks != first.break_even.medium.weeks
