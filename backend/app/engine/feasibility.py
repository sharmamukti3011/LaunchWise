"""Deterministic feasibility math for a business option.

Pure functions only: no network, DB or LLM. The agent tool and the What-If simulator
both call `run_feasibility`, so the same inputs always give the same numbers.
Money is `Decimal` in rupees, rounded half-up to paise. Floats are rejected.
"""

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Annotated, Any

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

PAISE = Decimal("0.01")
HUNDRED = Decimal("100")

# ASSUMPTION (not a measured figure): share of weekly capacity actually sold.
DEMAND_LOW = Decimal("0.25")
DEMAND_MEDIUM = Decimal("0.50")
DEMAND_HIGH = Decimal("1.00")


def _reject_float(value: Any) -> Any:
    if isinstance(value, float):
        raise ValueError("money must be a Decimal, string or int, never a float")
    return value


Money = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    Field(ge=0, allow_inf_nan=False),
]


class ConstraintProfile(BaseModel):
    """The entrepreneur's real constraints."""

    model_config = ConfigDict(frozen=True)

    budget: Money
    units_per_day: Annotated[int, Field(ge=0)]
    days_per_week: Annotated[int, Field(ge=0, le=7)]


class BusinessOption(BaseModel):
    """One business option to evaluate (the original idea is always one of them)."""

    model_config = ConfigDict(frozen=True)

    price: Money
    variable_cost_per_unit: Money
    fixed_startup_costs: Money


class BudgetCheck(BaseModel):
    model_config = ConfigDict(frozen=True)

    within_budget: bool
    startup_cost: Decimal
    budget: Decimal
    headroom: Decimal
    shortfall: Decimal


class BreakEvenPoint(BaseModel):
    """Break-even at one demand level. `weeks` is None when it is never reached."""

    model_config = ConfigDict(frozen=True)

    weekly_units: Decimal
    weeks: int | None


class BreakEvenByDemand(BaseModel):
    model_config = ConfigDict(frozen=True)

    low: BreakEvenPoint
    medium: BreakEvenPoint
    high: BreakEvenPoint


class FeasibilityResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    startup_cost: Decimal
    unit_variable_cost: Decimal
    contribution_margin: Decimal
    contribution_margin_pct: Decimal | None
    weekly_capacity: int
    max_weekly_revenue: Decimal
    break_even_units: int | None
    break_even: BreakEvenByDemand
    budget_check: BudgetCheck


def _paise(value: Decimal) -> Decimal:
    return value.quantize(PAISE, rounding=ROUND_HALF_UP)


def _ceil_div(numerator: Decimal, denominator: Decimal) -> int:
    return int((numerator / denominator).to_integral_value(rounding=ROUND_CEILING))


def _break_even_point(
    weekly_capacity: int, level: Decimal, units_needed: int | None
) -> BreakEvenPoint:
    weekly_units = Decimal(weekly_capacity) * level
    if units_needed is None or weekly_units == 0:
        return BreakEvenPoint(weekly_units=weekly_units, weeks=None)
    return BreakEvenPoint(
        weekly_units=weekly_units, weeks=_ceil_div(Decimal(units_needed), weekly_units)
    )


def run_feasibility(profile: ConstraintProfile, option: BusinessOption) -> FeasibilityResult:
    """Compute feasibility figures for `option` under `profile`."""
    price = _paise(option.price)
    unit_cost = _paise(option.variable_cost_per_unit)
    startup_cost = _paise(option.fixed_startup_costs)
    budget = _paise(profile.budget)

    margin = price - unit_cost
    margin_pct = _paise(margin / price * HUNDRED) if price > 0 else None

    weekly_capacity = profile.units_per_day * profile.days_per_week
    max_weekly_revenue = _paise(price * weekly_capacity)

    units_needed = _ceil_div(startup_cost, margin) if margin > 0 else None

    return FeasibilityResult(
        startup_cost=startup_cost,
        unit_variable_cost=unit_cost,
        contribution_margin=margin,
        contribution_margin_pct=margin_pct,
        weekly_capacity=weekly_capacity,
        max_weekly_revenue=max_weekly_revenue,
        break_even_units=units_needed,
        break_even=BreakEvenByDemand(
            low=_break_even_point(weekly_capacity, DEMAND_LOW, units_needed),
            medium=_break_even_point(weekly_capacity, DEMAND_MEDIUM, units_needed),
            high=_break_even_point(weekly_capacity, DEMAND_HIGH, units_needed),
        ),
        budget_check=BudgetCheck(
            within_budget=startup_cost <= budget,
            startup_cost=startup_cost,
            budget=budget,
            headroom=max(budget - startup_cost, Decimal("0.00")),
            shortfall=max(startup_cost - budget, Decimal("0.00")),
        ),
    )
