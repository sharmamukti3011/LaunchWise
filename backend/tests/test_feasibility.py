"""Feasibility engine tests. All money is Decimal; numbers are exact and reproducible."""

from decimal import Decimal
from typing import Any, get_args

import pytest
from pydantic import BaseModel, ValidationError

from app.engine.feasibility import (
    BusinessOption,
    FeasibilityInputs,
    FeasibilityResult,
    Source,
    Sourced,
    run_feasibility,
)

D = Decimal


def _inputs(
    budget: str = "10000", units_per_day: int = 3, days_per_week: int = 2
) -> FeasibilityInputs:
    return FeasibilityInputs(
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
    result = run_feasibility(_inputs(), _option())

    assert result.startup_cost.value == D("6000.00")
    assert result.unit_variable_cost.value == D("350.00")
    assert result.contribution_margin.value == D("450.00")
    assert result.contribution_margin_pct.value == D("56.25")
    assert result.weekly_capacity.value == 6
    assert result.max_weekly_revenue.value == D("4800.00")
    assert result.budget_check.within_budget is True
    assert result.budget_check.headroom.value == D("4000.00")
    assert result.budget_check.shortfall.value == D("0.00")

    # ceil(6000 / 450) = 14 units to recover startup cost.
    assert result.break_even_units.value == 14
    assert result.break_even.high.weekly_units.value == D("6")
    assert result.break_even.high.weeks.value == 3  # ceil(14 / 6)
    assert result.break_even.medium.weekly_units.value == D("3")
    assert result.break_even.medium.weeks.value == 5  # ceil(14 / 3)
    assert result.break_even.low.weekly_units.value == D("1.5")
    assert result.break_even.low.weeks.value == 10  # ceil(14 / 1.5)


def test_zero_margin_never_breaks_even() -> None:
    result = run_feasibility(_inputs(), _option(price="350", variable_cost="350"))

    assert result.contribution_margin.value == D("0.00")
    assert result.contribution_margin_pct.value == D("0.00")
    assert result.break_even_units.value is None
    assert result.break_even.low.weeks.value is None
    assert result.break_even.medium.weeks.value is None
    assert result.break_even.high.weeks.value is None


def test_negative_margin_never_breaks_even() -> None:
    result = run_feasibility(_inputs(), _option(price="300", variable_cost="350"))

    assert result.contribution_margin.value == D("-50.00")
    assert result.contribution_margin_pct.value == D("-16.67")
    assert result.break_even_units.value is None
    assert result.break_even.high.weeks.value is None
    # Capacity and revenue are still reported honestly.
    assert result.max_weekly_revenue.value == D("1800.00")


def test_over_budget_reports_shortfall() -> None:
    result = run_feasibility(_inputs(budget="5000"), _option(fixed="6000"))

    assert result.budget_check.within_budget is False
    assert result.budget_check.headroom.value == D("0.00")
    assert result.budget_check.shortfall.value == D("1000.00")


def test_exactly_on_budget_is_within_budget() -> None:
    result = run_feasibility(_inputs(budget="6000"), _option(fixed="6000"))

    assert result.budget_check.within_budget is True
    assert result.budget_check.headroom.value == D("0.00")
    assert result.budget_check.shortfall.value == D("0.00")


def test_one_unit_per_day() -> None:
    result = run_feasibility(_inputs(units_per_day=1), _option())

    assert result.weekly_capacity.value == 2
    assert result.max_weekly_revenue.value == D("1600.00")
    assert result.break_even_units.value == 14
    assert result.break_even.high.weeks.value == 7  # ceil(14 / 2)
    assert result.break_even.medium.weeks.value == 14  # ceil(14 / 1)
    assert result.break_even.low.weeks.value == 28  # ceil(14 / 0.5)


def test_zero_days_available() -> None:
    result = run_feasibility(_inputs(days_per_week=0), _option())

    assert result.weekly_capacity.value == 0
    assert result.max_weekly_revenue.value == D("0.00")
    # Margin is positive but nothing can be sold, so break-even is unreachable.
    assert result.contribution_margin.value == D("450.00")
    assert result.break_even_units.value == 14
    assert result.break_even.low.weeks.value is None
    assert result.break_even.medium.weeks.value is None
    assert result.break_even.high.weeks.value is None


def test_very_high_price_stays_exact() -> None:
    result = run_feasibility(_inputs(), _option(price="99999999.99", variable_cost="350"))

    assert result.contribution_margin.value == D("99999649.99")
    assert result.max_weekly_revenue.value == D("599999999.94")
    assert result.break_even_units.value == 1
    assert result.break_even.high.weeks.value == 1
    assert result.break_even.low.weeks.value == 1  # ceil(1 / 1.5)


def test_zero_price_has_no_margin_percentage() -> None:
    result = run_feasibility(_inputs(), _option(price="0", variable_cost="0"))

    assert result.contribution_margin_pct.value is None
    assert result.break_even_units.value is None


def test_money_rounds_half_up_to_paise() -> None:
    result = run_feasibility(_inputs(), _option(price="100.005", variable_cost="0"))

    assert result.contribution_margin.value == D("100.01")


def test_result_money_is_decimal_not_float() -> None:
    result = run_feasibility(_inputs(), _option(), include_working_capital=True)
    assert result.budget_check.working_capital is not None

    for figure in (
        result.startup_cost,
        result.unit_variable_cost,
        result.contribution_margin,
        result.contribution_margin_pct,
        result.max_weekly_revenue,
        result.budget_check.headroom,
        result.budget_check.shortfall,
        result.budget_check.working_capital,
        result.budget_check.total_required,
    ):
        assert isinstance(figure.value, Decimal)


def test_float_money_is_rejected() -> None:
    with pytest.raises(ValidationError):
        FeasibilityInputs(budget=10000.5, units_per_day=3, days_per_week=2)
    with pytest.raises(ValidationError):
        BusinessOption(
            price=800.0,
            variable_cost_per_unit=D("350"),
            fixed_startup_costs=D("6000"),
        )


# --- Negative money is rejected (budget, price, variable cost, fixed startup costs) ---

NEGATIVES = ["-0.01", "-1", "-10000"]


@pytest.mark.parametrize("amount", NEGATIVES)
def test_negative_budget_is_rejected(amount: str) -> None:
    with pytest.raises(ValidationError):
        _inputs(budget=amount)


@pytest.mark.parametrize("amount", NEGATIVES)
def test_negative_price_is_rejected(amount: str) -> None:
    with pytest.raises(ValidationError):
        _option(price=amount)


@pytest.mark.parametrize("amount", NEGATIVES)
def test_negative_variable_cost_is_rejected(amount: str) -> None:
    with pytest.raises(ValidationError):
        _option(variable_cost=amount)


@pytest.mark.parametrize("amount", NEGATIVES)
def test_negative_fixed_startup_costs_are_rejected(amount: str) -> None:
    with pytest.raises(ValidationError):
        _option(fixed=amount)


@pytest.mark.parametrize("amount", ["NaN", "Infinity", "-Infinity"])
def test_non_finite_money_is_rejected(amount: str) -> None:
    with pytest.raises(ValidationError):
        _inputs(budget=amount)
    with pytest.raises(ValidationError):
        _option(price=amount)


def test_zero_money_is_accepted() -> None:
    result = run_feasibility(_inputs(budget="0"), _option(price="0", variable_cost="0", fixed="0"))

    assert result.budget_check.within_budget is True


@pytest.mark.parametrize(
    "kwargs",
    [
        {"units_per_day": -1},
        {"days_per_week": 8},
        {"days_per_week": -1},
    ],
)
def test_invalid_capacity_inputs_are_rejected(kwargs: dict[str, object]) -> None:
    base: dict[str, object] = {"budget": D("10000"), "units_per_day": 3, "days_per_week": 2}
    with pytest.raises(ValidationError):
        FeasibilityInputs(**{**base, **kwargs})


def test_deterministic_and_what_if_reuses_same_function() -> None:
    inputs, option = _inputs(), _option()
    first = run_feasibility(inputs, option)
    assert run_feasibility(inputs, option) == first

    # What-If: raising the price changes margin and shortens break-even.
    what_if: FeasibilityResult = run_feasibility(inputs, _option(price="1000"))
    assert what_if.contribution_margin.value == D("650.00")
    assert what_if.break_even_units.value == 10  # ceil(6000 / 650)
    assert what_if.break_even.medium.weeks.value == 4  # ceil(10 / 3)
    assert what_if.break_even.medium.weeks.value != first.break_even.medium.weeks.value


# --- Source tags ---


def _untagged_figures(model: BaseModel, path: str = "") -> list[str]:
    """Names of numeric fields not wrapped in Sourced (bool verdicts and omitted lines exempt)."""
    untagged: list[str] = []
    for name in type(model).model_fields:
        value: Any = getattr(model, name)
        where = f"{path}{name}"
        if value is None or isinstance(value, Sourced):
            continue  # an omitted optional line (e.g. working capital) has nothing to tag
        if isinstance(value, BaseModel):
            untagged.extend(_untagged_figures(value, f"{where}."))
        elif not isinstance(value, bool):
            untagged.append(where)
    return untagged


@pytest.mark.parametrize("working_capital", [False, True])
def test_every_output_figure_carries_a_source(working_capital: bool) -> None:
    result = run_feasibility(_inputs(), _option(), include_working_capital=working_capital)

    assert _untagged_figures(result) == []


def test_sources_are_limited_to_the_three_allowed_tags() -> None:
    assert set(get_args(Source)) == {"user_provided", "assumption", "estimate"}
    with pytest.raises(ValidationError):
        Sourced[int](value=1, source="verified")


def test_inputs_are_echoed_as_user_provided() -> None:
    result = run_feasibility(_inputs(), _option())
    echo = result.inputs

    assert (echo.budget.value, echo.budget.source) == (D("10000.00"), "user_provided")
    assert (echo.units_per_day.value, echo.units_per_day.source) == (3, "user_provided")
    assert (echo.days_per_week.value, echo.days_per_week.source) == (2, "user_provided")
    assert (echo.price.value, echo.price.source) == (D("800.00"), "user_provided")
    assert echo.variable_cost_per_unit.value == D("350.00")
    assert echo.variable_cost_per_unit.source == "user_provided"
    assert echo.fixed_startup_costs.value == D("6000.00")
    assert echo.fixed_startup_costs.source == "user_provided"


def test_figures_from_user_inputs_alone_are_user_provided() -> None:
    result = run_feasibility(_inputs(), _option())

    for figure in (
        result.startup_cost,
        result.unit_variable_cost,
        result.contribution_margin,
        result.contribution_margin_pct,
        result.weekly_capacity,
        result.max_weekly_revenue,
        result.break_even_units,
        result.budget_check.budget,
        result.budget_check.headroom,
        result.budget_check.shortfall,
        result.budget_check.total_required,
    ):
        assert figure.source == "user_provided"


def test_demand_factors_are_tagged_assumptions() -> None:
    result = run_feasibility(_inputs(), _option())
    by_demand = result.break_even

    assert (by_demand.low.demand_factor.value, by_demand.low.demand_factor.source) == (
        D("0.25"),
        "assumption",
    )
    assert (by_demand.medium.demand_factor.value, by_demand.medium.demand_factor.source) == (
        D("0.50"),
        "assumption",
    )
    assert (by_demand.high.demand_factor.value, by_demand.high.demand_factor.source) == (
        D("1.00"),
        "assumption",
    )


def test_figures_that_depend_on_demand_factors_are_estimates() -> None:
    result = run_feasibility(_inputs(), _option())

    for point in (result.break_even.low, result.break_even.medium, result.break_even.high):
        assert point.weekly_units.source == "estimate"
        assert point.weeks.source == "estimate"


def test_unreachable_break_even_is_still_tagged() -> None:
    result = run_feasibility(_inputs(days_per_week=0), _option())

    assert result.break_even.low.weeks.value is None
    assert result.break_even.low.weeks.source == "estimate"
    assert _untagged_figures(result) == []


# --- Working capital ---


def test_working_capital_is_off_by_default() -> None:
    result = run_feasibility(_inputs(), _option())

    assert result.budget_check.working_capital is None
    assert result.budget_check.total_required.value == D("6000.00")


def test_working_capital_is_first_week_variable_cost_at_full_capacity() -> None:
    result = run_feasibility(_inputs(), _option(), include_working_capital=True)
    check = result.budget_check

    assert check.working_capital is not None
    assert check.working_capital.value == D("2100.00")  # 6 units x Rs 350
    assert check.working_capital.source == "assumption"
    assert check.total_required.value == D("8100.00")
    # Totals that include the assumed working capital inherit the assumption tag.
    assert check.total_required.source == "assumption"
    assert check.headroom.source == "assumption"
    assert check.shortfall.source == "assumption"
    assert check.within_budget is True
    assert check.headroom.value == D("1900.00")
    assert check.shortfall.value == D("0.00")


def test_working_capital_can_tip_a_plan_over_budget() -> None:
    inputs, option = _inputs(budget="7000"), _option()

    assert run_feasibility(inputs, option).budget_check.within_budget is True

    check = run_feasibility(inputs, option, include_working_capital=True).budget_check
    assert check.within_budget is False
    assert check.total_required.value == D("8100.00")
    assert check.shortfall.value == D("1100.00")
    assert check.headroom.value == D("0.00")
    # The upfront startup cost itself is unchanged.
    assert check.startup_cost.value == D("6000.00")


def test_working_capital_is_zero_when_nothing_can_be_made() -> None:
    result = run_feasibility(_inputs(days_per_week=0), _option(), include_working_capital=True)

    assert result.budget_check.working_capital is not None
    assert result.budget_check.working_capital.value == D("0.00")
    assert result.budget_check.total_required.value == D("6000.00")
