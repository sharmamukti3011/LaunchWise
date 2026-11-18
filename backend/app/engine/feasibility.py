"""Deterministic feasibility math for a business option.

Pure functions only: no network, DB or LLM. The agent tool and the What-If simulator
both call `run_feasibility`, so the same inputs always give the same numbers.
Money is `Decimal` in rupees, rounded half-up to paise. Floats are rejected.

Every numeric output figure is wrapped in `Sourced` with a tag callers can display:
- `user_provided`: an input echo, or arithmetic on user inputs alone.
- `assumption`: a value we chose (demand factors, working capital), not measured.
- `estimate`: derived using an assumption, so it is only as good as that assumption.
The `within_budget` verdict is a plain bool and is not tagged.
"""

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal
from typing import Annotated, Any, Generic, Literal, TypeVar

from pydantic import BaseModel, BeforeValidator, ConfigDict, Field

PAISE = Decimal("0.01")
HUNDRED = Decimal("100")
ZERO_MONEY = Decimal("0.00")

# ASSUMPTION (not a measured figure): share of weekly capacity actually sold.
DEMAND_LOW = Decimal("0.25")
DEMAND_MEDIUM = Decimal("0.50")
DEMAND_HIGH = Decimal("1.00")

Source = Literal["user_provided", "assumption", "estimate"]

T = TypeVar("T")


class Sourced(BaseModel, Generic[T]):  # noqa: UP046 - keep Python 3.11 compatible
    """A figure plus where it came from. Unknown keys are rejected."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    value: T
    source: Source


def _user(value: T) -> Sourced[T]:
    return Sourced[T](value=value, source="user_provided")


def _assumed(value: T) -> Sourced[T]:
    return Sourced[T](value=value, source="assumption")


def _estimated(value: T) -> Sourced[T]:
    return Sourced[T](value=value, source="estimate")


def _reject_float(value: Any) -> Any:
    if isinstance(value, float):
        raise ValueError("money must be a Decimal, string or int, never a float")
    return value


# Negative, NaN and infinite amounts are rejected here, at the boundary.
Money = Annotated[
    Decimal,
    BeforeValidator(_reject_float),
    Field(ge=0, allow_inf_nan=False),
]


class FeasibilityInputs(BaseModel):
    """The capacity and budget constraints the engine needs."""

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


class InputEcho(BaseModel):
    """The inputs as the engine used them (money rounded to paise)."""

    model_config = ConfigDict(frozen=True)

    budget: Sourced[Decimal]
    units_per_day: Sourced[int]
    days_per_week: Sourced[int]
    price: Sourced[Decimal]
    variable_cost_per_unit: Sourced[Decimal]
    fixed_startup_costs: Sourced[Decimal]


class BudgetCheck(BaseModel):
    """`working_capital` is None unless requested. When present it counts toward the budget."""

    model_config = ConfigDict(frozen=True)

    within_budget: bool
    budget: Sourced[Decimal]
    startup_cost: Sourced[Decimal]
    working_capital: Sourced[Decimal] | None
    total_required: Sourced[Decimal]
    headroom: Sourced[Decimal]
    shortfall: Sourced[Decimal]


class BreakEvenPoint(BaseModel):
    """Break-even at one demand level. `weeks.value` is None when it is never reached."""

    model_config = ConfigDict(frozen=True)

    demand_factor: Sourced[Decimal]
    weekly_units: Sourced[Decimal]
    weeks: Sourced[int | None]


class BreakEvenByDemand(BaseModel):
    model_config = ConfigDict(frozen=True)

    low: BreakEvenPoint
    medium: BreakEvenPoint
    high: BreakEvenPoint


class FeasibilityResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    inputs: InputEcho
    startup_cost: Sourced[Decimal]
    unit_variable_cost: Sourced[Decimal]
    contribution_margin: Sourced[Decimal]
    contribution_margin_pct: Sourced[Decimal | None]
    weekly_capacity: Sourced[int]
    max_weekly_revenue: Sourced[Decimal]
    break_even_units: Sourced[int | None]
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
    weeks = (
        None
        if units_needed is None or weekly_units == 0
        else _ceil_div(Decimal(units_needed), weekly_units)
    )
    return BreakEvenPoint(
        demand_factor=_assumed(level),
        weekly_units=_estimated(weekly_units),
        weeks=_estimated(weeks),
    )


def run_feasibility(
    inputs: FeasibilityInputs,
    option: BusinessOption,
    *,
    include_working_capital: bool = False,
) -> FeasibilityResult:
    """Compute feasibility figures for `option` under `inputs`.

    With `include_working_capital`, the budget check also reserves the first week's variable
    cost at full capacity (an assumption) and compares the total against the budget.
    """
    price = _paise(option.price)
    unit_cost = _paise(option.variable_cost_per_unit)
    startup_cost = _paise(option.fixed_startup_costs)
    budget = _paise(inputs.budget)

    margin = price - unit_cost
    margin_pct = _paise(margin / price * HUNDRED) if price > 0 else None

    weekly_capacity = inputs.units_per_day * inputs.days_per_week
    max_weekly_revenue = _paise(price * weekly_capacity)

    units_needed = _ceil_div(startup_cost, margin) if margin > 0 else None

    working_capital = _paise(unit_cost * weekly_capacity) if include_working_capital else None
    total_required = startup_cost + (working_capital or ZERO_MONEY)
    # Totals that include working capital inherit its assumption tag.
    total_tag = _assumed if include_working_capital else _user

    return FeasibilityResult(
        inputs=InputEcho(
            budget=_user(budget),
            units_per_day=_user(inputs.units_per_day),
            days_per_week=_user(inputs.days_per_week),
            price=_user(price),
            variable_cost_per_unit=_user(unit_cost),
            fixed_startup_costs=_user(startup_cost),
        ),
        startup_cost=_user(startup_cost),
        unit_variable_cost=_user(unit_cost),
        contribution_margin=_user(margin),
        contribution_margin_pct=_user(margin_pct),
        weekly_capacity=_user(weekly_capacity),
        max_weekly_revenue=_user(max_weekly_revenue),
        break_even_units=_user(units_needed),
        break_even=BreakEvenByDemand(
            low=_break_even_point(weekly_capacity, DEMAND_LOW, units_needed),
            medium=_break_even_point(weekly_capacity, DEMAND_MEDIUM, units_needed),
            high=_break_even_point(weekly_capacity, DEMAND_HIGH, units_needed),
        ),
        budget_check=BudgetCheck(
            within_budget=total_required <= budget,
            budget=_user(budget),
            startup_cost=_user(startup_cost),
            working_capital=None if working_capital is None else _assumed(working_capital),
            total_required=total_tag(total_required),
            headroom=total_tag(max(budget - total_required, ZERO_MONEY)),
            shortfall=total_tag(max(total_required - budget, ZERO_MONEY)),
        ),
    )
