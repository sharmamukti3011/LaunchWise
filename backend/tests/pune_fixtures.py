"""Shared Pune bakery fixtures: Rs 10,000, 3 cakes/day, weekends only (6 units a week).

hours_per_week and minutes_per_unit are assumptions here, not user data.
Opportunities are obviously fake test fixtures (ids TEST-FAKE-*, label test_fixture).
"""

from datetime import date
from decimal import Decimal
from typing import Any

from app.engine.feasibility import BusinessOption, FeasibilityResult, Sourced, run_feasibility
from app.services.profile_mapper import to_feasibility_inputs
from app.services.strategy_models import ConstraintProfile, Opportunity, StrategyOption

D = Decimal
TODAY = date(2026, 11, 17)


def assumed(value: int) -> Sourced[int]:
    return Sourced[int](value=value, source="assumption")


def profile(**overrides: Any) -> ConstraintProfile:
    data: dict[str, Any] = {
        "budget": D("10000"),
        "units_per_day": 3,
        "days_per_week": 2,
        "hours_per_week": assumed(12),
        "skills": ["baking", "decorating"],
        "equipment": ["oven", "mixer"],
        "location": "Pune",
    }
    data.update(overrides)
    return ConstraintProfile(**data)


def option(**overrides: Any) -> StrategyOption:
    data: dict[str, Any] = {
        "id": "orig",
        "title": "Home bakery",
        "is_original": True,
        "price": D("800"),
        "variable_cost_per_unit": D("350"),
        "fixed_startup_costs": D("6000"),
        "minutes_per_unit": assumed(90),
    }
    data.update(overrides)
    return StrategyOption(**data)


def feasibility(
    opt: StrategyOption | None = None, prof: ConstraintProfile | None = None
) -> FeasibilityResult:
    opt = opt or option()
    return run_feasibility(
        to_feasibility_inputs(prof or profile()),
        BusinessOption(
            price=opt.price,
            variable_cost_per_unit=opt.variable_cost_per_unit,
            fixed_startup_costs=opt.fixed_startup_costs,
        ),
        include_working_capital=True,
    )


def opportunity(**overrides: Any) -> Opportunity:
    data: dict[str, Any] = {
        "id": "TEST-FAKE-001",
        "title": "Test fixture opportunity",
        "location": "Pune",
        "category": "bakery",
        "signal_summary": "Fake signal.",
        "evidence": "Fake evidence.",
        "source_name": "test_fixture",
        "source_url": "https://example.invalid/test-fixture",
        "event_date": date(2027, 1, 10),
        "retrieved_date": date(2026, 11, 1),
        "verification_status": "verified",
        "verified_by": "test_fixture",
        "verified_on": date(2026, 11, 2),
        "signal_strength": "high",
        "required_skills": [],
        "required_equipment": [],
        "lead_time_days": 7,
        "label": "test_fixture",
    }
    data.update(overrides)
    return Opportunity(**data)
