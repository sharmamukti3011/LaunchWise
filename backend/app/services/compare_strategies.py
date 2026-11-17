"""Rank business options deterministically. No Claude, no I/O: the clock and dataset are passed in.

Each option is run through the feasibility engine (with working capital) and scored on five
dimensions (see `scoring.py`). The total is a weighted sum. Viable options always outrank
non-viable ones, and a recommendation is only made when at least one option is viable.
"""

from datetime import date
from decimal import Decimal

from app.engine.feasibility import BusinessOption, FeasibilityResult, run_feasibility
from app.services.profile_mapper import to_feasibility_inputs
from app.services.scoring import (
    budget_fit,
    capacity_fit,
    margin_fit,
    market_signal_fit,
    skill_equipment_fit,
)
from app.services.strategy_models import (
    ConstraintProfile,
    DimensionName,
    DimensionScore,
    Opportunity,
    OptionScore,
    RankedStrategies,
    StrategyOption,
)

# ASSUMPTION (our choice, not measured): how much each dimension counts. Sums to 100.
WEIGHTS: dict[DimensionName, int] = {
    "margin": 30,
    "budget": 20,
    "capacity": 20,
    "skill_equipment": 15,
    "market_signal": 15,
}
TOTAL_WEIGHT = Decimal(100)
TOTAL_PLACES = Decimal("0.01")


class StrategyComparisonError(ValueError):
    """The options or opportunities handed to `compare_strategies` are inconsistent."""


def _validate(options: list[StrategyOption], opportunities: list[Opportunity]) -> None:
    if len([o for o in options if o.is_original]) != 1:
        raise StrategyComparisonError("exactly one original option is required")
    option_ids = [o.id for o in options]
    if len(set(option_ids)) != len(option_ids):
        raise StrategyComparisonError("duplicate option id")
    opportunity_ids = [o.id for o in opportunities]
    if len(set(opportunity_ids)) != len(opportunity_ids):
        raise StrategyComparisonError("duplicate opportunity id")
    for option in options:
        if option.opportunity_id is None:
            if not option.is_original:
                raise StrategyComparisonError(
                    f"option {option.id!r} has no opportunity_id; only the original may omit it"
                )
        elif option.opportunity_id not in opportunity_ids:
            raise StrategyComparisonError(
                f"option {option.id!r} refers to unknown opportunity_id {option.opportunity_id!r}"
            )


def _viability_issues(
    result: FeasibilityResult, opportunity: Opportunity | None, today: date
) -> list[str]:
    issues = []
    if not result.budget_check.within_budget:
        issues.append("over budget")
    if result.contribution_margin.value <= 0:
        issues.append("no positive margin")
    if opportunity is not None and opportunity.has_passed(today):
        issues.append("event passed")
    return issues


def _score_option(
    profile: ConstraintProfile,
    option: StrategyOption,
    opportunity: Opportunity | None,
    today: date,
) -> OptionScore:
    result = run_feasibility(
        to_feasibility_inputs(profile),
        BusinessOption(
            price=option.price,
            variable_cost_per_unit=option.variable_cost_per_unit,
            fixed_startup_costs=option.fixed_startup_costs,
        ),
        include_working_capital=True,
    )
    scores: list[DimensionScore] = [
        margin_fit(result),
        budget_fit(result),
        capacity_fit(profile, option, result),
        skill_equipment_fit(profile, option),
        market_signal_fit(option, opportunity, today),
    ]
    weighted = sum(Decimal(s.score * WEIGHTS[s.dimension]) for s in scores)
    issues = _viability_issues(result, opportunity, today)
    return OptionScore(
        option_id=option.id,
        title=option.title,
        is_original=option.is_original,
        scores=scores,
        total=(weighted / TOTAL_WEIGHT).quantize(TOTAL_PLACES),
        viable=not issues,
        viability_issues=issues,
    )


def compare_strategies(
    profile: ConstraintProfile,
    options: list[StrategyOption],
    opportunities: list[Opportunity],
    today: date,
) -> RankedStrategies:
    _validate(options, opportunities)
    by_id = {o.id: o for o in opportunities}
    scored = [
        _score_option(
            profile,
            option,
            by_id[option.opportunity_id] if option.opportunity_id else None,
            today,
        )
        for option in options
    ]
    # Viable first, then higher total, then the original idea, then id for a stable order.
    scored.sort(key=lambda s: (not s.viable, -s.total, not s.is_original, s.option_id))
    best = scored[0]
    recommended = best if best.viable else None
    return RankedStrategies(
        ranked=scored,
        recommended_id=recommended.option_id if recommended else None,
        keep_original=recommended is not None and recommended.is_original,
    )
