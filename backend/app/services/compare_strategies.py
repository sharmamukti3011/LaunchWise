"""Rank business options deterministically. No Claude, no I/O: the clock and dataset are passed in.

Each option is run through the feasibility engine (with working capital) and scored on five
dimensions (see `scoring.py`). The total is a weighted sum. Viable options always outrank
non-viable ones, and a recommendation is only made when at least one option is viable.
"""

from datetime import date
from decimal import Decimal

from app.engine.feasibility import (
    HUNDRED,
    BusinessOption,
    FeasibilityResult,
    run_feasibility,
)
from app.services.profile_mapper import to_feasibility_inputs
from app.services.scoring import (
    NO_EVIDENCE_SCORE,
    budget_fit,
    capacity_fit,
    margin_fit,
    market_signal_fit,
    missing_items,
    rupees,
    skill_equipment_fit,
)
from app.services.strategy_models import (
    Caveat,
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


# How a source below "verified" is put to the owner, in plain words.
_WEAK_VERIFICATION = {
    "single_source": "rests on a single source",
    "unverified_sample": "has not been checked yet",
}


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
    result: FeasibilityResult,
    scores: list[DimensionScore],
    opportunity: Opportunity | None,
    today: date,
) -> list[str]:
    issues = []
    if not result.budget_check.within_budget:
        issues.append("over budget")
    if result.contribution_margin.value <= 0:
        issues.append("no positive margin")
    if opportunity is not None and opportunity.has_passed(today):
        issues.append("event passed")
    # A zero here means the plan cannot be run at all, however well it scores elsewhere.
    by_dimension = {s.dimension: s for s in scores}
    gates: list[tuple[DimensionName, str]] = [
        ("skill_equipment", "skill and equipment"),
        ("capacity", "capacity"),
    ]
    for dimension, label in gates:
        gate = by_dimension[dimension]
        if gate.score == 0:
            issues.append(f"{label} fit is 0 ({gate.reason})")
    return issues


def feasibility_for(profile: ConstraintProfile, option: StrategyOption) -> FeasibilityResult:
    """The engine result for one option, with working capital. The one place this is computed."""
    return run_feasibility(
        to_feasibility_inputs(profile),
        BusinessOption(
            price=option.price,
            variable_cost_per_unit=option.variable_cost_per_unit,
            fixed_startup_costs=option.fixed_startup_costs,
        ),
        include_working_capital=True,
    )


def _score_option(
    profile: ConstraintProfile,
    option: StrategyOption,
    result: FeasibilityResult,
    opportunity: Opportunity | None,
    today: date,
) -> OptionScore:
    scores: list[DimensionScore] = [
        margin_fit(result),
        budget_fit(result),
        capacity_fit(profile, option, result),
        skill_equipment_fit(profile, option),
        market_signal_fit(option, opportunity, today),
    ]
    weighted = sum(Decimal(s.score * WEIGHTS[s.dimension]) for s in scores)
    issues = _viability_issues(result, scores, opportunity, today)
    return OptionScore(
        option_id=option.id,
        title=option.title,
        is_original=option.is_original,
        scores=scores,
        total=(weighted / TOTAL_WEIGHT).quantize(TOTAL_PLACES),
        viable=not issues,
        viability_issues=issues,
    )


def _engine_assumption_caveats(result: FeasibilityResult) -> list[Caveat]:
    caveats: list[Caveat] = []
    working_capital = result.budget_check.working_capital
    if working_capital is not None:
        caveats.append(
            Caveat(
                kind="engine_assumption",
                message=(
                    f"Working capital reserve ({rupees(working_capital.value)}) is assumed: "
                    "the first week's running costs at full capacity."
                ),
                items=["working_capital"],
            )
        )
    levels = result.break_even
    shares = [
        f"{(point.demand_factor.value * HUNDRED).quantize(Decimal(1))}%"
        for point in (levels.low, levels.medium, levels.high)
    ]
    caveats.append(
        Caveat(
            kind="engine_assumption",
            message=(
                f"Demand is assumed: we modelled selling {shares[0]}, {shares[1]} and {shares[2]} "
                "of your weekly capacity."
            ),
            items=["demand_factors"],
        )
    )
    return caveats


def _caveats(
    profile: ConstraintProfile,
    option: StrategyOption,
    result: FeasibilityResult,
    opportunity: Opportunity | None,
) -> list[Caveat]:
    caveats: list[Caveat] = []
    for kind, noun, required, have in (
        ("missing_skills", "Skills", option.required_skills, profile.skills),
        ("missing_equipment", "Equipment", option.required_equipment, profile.equipment),
    ):
        missing = missing_items(required, have)
        if missing:
            message = f"{noun} this option needs that you haven't listed: {', '.join(missing)}."
            caveats.append(Caveat(kind=kind, message=message, items=missing))
    # Only inputs tagged "assumption" are caveated; user-provided figures are not. The message
    # is written for the owner; `items` keeps the field name for the API.
    for name, phrase, sourced in (
        ("hours_per_week", "Weekly hours available ({value})", profile.hours_per_week),
        ("minutes_per_unit", "Time per item ({value} minutes)", option.minutes_per_unit),
    ):
        if sourced.source == "assumption":
            text = phrase.format(value=sourced.value)
            caveats.append(
                Caveat(
                    kind="assumption",
                    message=f"{text} is assumed, not provided by you",
                    items=[name],
                )
            )
    caveats.extend(_engine_assumption_caveats(result))
    if opportunity is None:
        # Validation lets only the original omit a link, so this is the original idea.
        caveats.append(
            Caveat(
                kind="no_market_evidence",
                message=(
                    "There is no market evidence for your original idea, so its market score "
                    f"is a neutral {NO_EVIDENCE_SCORE}, not a finding."
                ),
                items=[],
            )
        )
    if opportunity is not None and opportunity.direction == "against":
        caveats.append(
            Caveat(
                kind="evidence_against",
                message=f"Market evidence {opportunity.id} argues against this option.",
                items=[opportunity.id],
            )
        )
    if opportunity is not None and opportunity.verification_status != "verified":
        how = _WEAK_VERIFICATION[opportunity.verification_status]
        caveats.append(
            Caveat(
                kind="verification",
                message=(
                    f"Market evidence {opportunity.id} {how}, so treat its signal with caution."
                ),
                items=[opportunity.id],
            )
        )
    return caveats


def _for_option(title: str, message: str) -> str:
    """'Premium cakes: working capital reserve ...' (the message's first letter lower-cased)."""
    return f"{title}: {message[:1].lower()}{message[1:]}"


def _caveats_for_all(
    profile: ConstraintProfile,
    ordered: list[StrategyOption],
    results: dict[str, FeasibilityResult],
    linked: dict[str, Opportunity | None],
) -> list[Caveat]:
    """Caveats when nothing is recommended: every option's, so the owner still sees what the
    "nothing is viable" verdict rests on. A caveat that is the same for every option (demand
    factors, weekly hours) is said once. One that differs (working capital, time per item, gaps
    in skills or equipment) is said per option with the option named. No message repeats."""
    per_option = [(o, _caveats(profile, o, results[o.id], linked[o.id])) for o in ordered]
    common = {c.message for c in per_option[0][1]}
    for _, caveats in per_option[1:]:
        common &= {c.message for c in caveats}
    out: list[Caveat] = []
    seen: set[tuple[str, str]] = set()

    def add(caveat: Caveat) -> None:
        key = (caveat.kind, caveat.message)
        if key not in seen:
            seen.add(key)
            out.append(caveat)

    for caveat in per_option[0][1]:
        if caveat.message in common:
            add(caveat)
    for option, caveats in per_option:
        for caveat in caveats:
            if caveat.message not in common:
                add(
                    caveat.model_copy(update={"message": _for_option(option.title, caveat.message)})
                )
    return out


def compare_strategies(
    profile: ConstraintProfile,
    options: list[StrategyOption],
    opportunities: list[Opportunity],
    today: date,
) -> RankedStrategies:
    _validate(options, opportunities)
    by_id = {o.id: o for o in opportunities}
    results = {option.id: feasibility_for(profile, option) for option in options}
    scored = [
        _score_option(
            profile,
            option,
            results[option.id],
            by_id[option.opportunity_id] if option.opportunity_id else None,
            today,
        )
        for option in options
    ]
    # Viable first, then higher total, then the original idea, then id for a stable order.
    scored.sort(key=lambda s: (not s.viable, -s.total, not s.is_original, s.option_id))
    best = scored[0]
    if not best.viable:
        by_option = {o.id: o for o in options}
        return RankedStrategies(
            ranked=scored,
            recommended_id=None,
            keep_original=False,
            caveats=_caveats_for_all(
                profile,
                [by_option[s.option_id] for s in scored],
                results,
                {o.id: by_id[o.opportunity_id] if o.opportunity_id else None for o in options},
            ),
        )
    chosen = next(o for o in options if o.id == best.option_id)
    linked = by_id[chosen.opportunity_id] if chosen.opportunity_id else None
    return RankedStrategies(
        ranked=scored,
        recommended_id=best.option_id,
        keep_original=best.is_original,
        caveats=_caveats(profile, chosen, results[chosen.id], linked),
    )
