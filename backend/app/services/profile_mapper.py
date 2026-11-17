"""Map the full constraint profile to the narrower input the feasibility engine takes."""

from app.engine.feasibility import FeasibilityInputs
from app.services.strategy_models import ConstraintProfile


def to_feasibility_inputs(profile: ConstraintProfile) -> FeasibilityInputs:
    return FeasibilityInputs(
        budget=profile.budget,
        units_per_day=profile.units_per_day,
        days_per_week=profile.days_per_week,
    )
