"""ConstraintProfile -> FeasibilityInputs mapping."""

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.engine.feasibility import FeasibilityInputs, Sourced
from app.services.profile_mapper import to_feasibility_inputs
from app.services.strategy_models import ConstraintProfile

D = Decimal


def pune_profile(**overrides: Any) -> ConstraintProfile:
    """Pune home bakery. Budget, units and days are user data; hours is our assumption."""
    data: dict[str, Any] = {
        "budget": D("10000"),
        "units_per_day": 3,
        "days_per_week": 2,
        "hours_per_week": Sourced[int](value=12, source="assumption"),
        "skills": ["baking", "decorating"],
        "equipment": ["oven", "mixer"],
        "location": "Pune",
    }
    data.update(overrides)
    return ConstraintProfile(**data)


def test_mapper_passes_only_engine_fields() -> None:
    inputs = to_feasibility_inputs(pune_profile())
    assert inputs == FeasibilityInputs(budget=D("10000"), units_per_day=3, days_per_week=2)


def test_mapper_ignores_non_engine_fields() -> None:
    a = to_feasibility_inputs(pune_profile(skills=[], equipment=[], location="Mumbai"))
    b = to_feasibility_inputs(pune_profile())
    assert a == b


def test_profile_rejects_float_budget() -> None:
    with pytest.raises(ValidationError):
        pune_profile(budget=10000.0)


def test_profile_rejects_negative_budget() -> None:
    with pytest.raises(ValidationError):
        pune_profile(budget=D("-1"))


@pytest.mark.parametrize("days", [-1, 8])
def test_profile_rejects_bad_days(days: int) -> None:
    with pytest.raises(ValidationError):
        pune_profile(days_per_week=days)


def test_profile_rejects_more_hours_than_a_week_has() -> None:
    with pytest.raises(ValidationError):
        pune_profile(hours_per_week=Sourced[int](value=169, source="assumption"))


def test_profile_is_immutable() -> None:
    with pytest.raises(ValidationError):
        pune_profile().budget = D("1")  # type: ignore[misc]
