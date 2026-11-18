"""Deterministic 0-100 scorers, one per dimension, each with a reason built from real figures.

Every threshold below is a named constant and an ASSUMPTION we chose, not a measured value.
Scorers take the engine's `FeasibilityResult` (computed with `include_working_capital=True`)
and never recompute its numbers.
"""

from datetime import date
from decimal import ROUND_FLOOR, ROUND_HALF_UP, Decimal

from app.engine.feasibility import HUNDRED, PAISE, FeasibilityResult, Source
from app.services.strategy_models import (
    ConstraintProfile,
    DimensionScore,
    Opportunity,
    SignalStrength,
    StrategyOption,
)

MINUTES_PER_HOUR = Decimal(60)

# Margin at or above this share of price scores 100; below it the score is linear.
FULL_MARK_MARGIN_PCT = Decimal(50)

# A plan that fits the budget scores at least this; extra headroom (as a share of budget) adds.
WITHIN_BUDGET_FLOOR = 50

# No market evidence (the user's own idea) is neutral, neither good nor bad.
NO_EVIDENCE_SCORE = 50
SIGNAL_POINTS: dict[SignalStrength, int] = {"low": 30, "medium": 60, "high": 90}
UNVERIFIED_DEDUCTION = 15


def _group_indian(digits: str) -> str:
    """12345678 -> 1,23,45,678: the grouping people in India read, and the screen uses."""
    if len(digits) <= 3:
        return digits
    head, tail = digits[:-3], digits[-3:]
    groups: list[str] = []
    while len(head) > 2:
        groups.insert(0, head[-2:])
        head = head[:-2]
    if head:
        groups.insert(0, head)
    return ",".join([*groups, tail])


def rupees(value: Decimal) -> str:
    """₹10,000 for a whole-rupee amount; paise only when the value is not whole (₹900.50)."""
    amount = value.quantize(PAISE, rounding=ROUND_HALF_UP)
    sign = "-" if amount < 0 else ""
    whole, _, paise = f"{abs(amount):f}".partition(".")
    shown = _group_indian(whole)
    return f"{sign}₹{shown}" if paise == "00" else f"{sign}₹{shown}.{paise}"


def _floor_int(value: Decimal) -> int:
    return int(value.to_integral_value(rounding=ROUND_FLOOR))


def _label(source: Source) -> str:
    return source.replace("_", " ")


def _clamp(value: int) -> int:
    return max(0, min(100, value))


def margin_fit(result: FeasibilityResult) -> DimensionScore:
    pct = result.contribution_margin_pct.value
    margin = result.contribution_margin.value
    if pct is None:
        return DimensionScore(dimension="margin", score=0, reason="no price, so no margin")
    if margin <= 0:
        return DimensionScore(
            dimension="margin",
            score=0,
            reason=f"margin {pct}% of price ({rupees(margin)} per unit) leaves nothing to earn",
        )
    score = _clamp(_floor_int(pct / FULL_MARK_MARGIN_PCT * HUNDRED))
    medium = result.break_even.medium
    weekly = margin * medium.weekly_units.value
    share = (medium.demand_factor.value * HUNDRED).quantize(Decimal(1))
    return DimensionScore(
        dimension="margin",
        score=score,
        reason=(
            f"margin {pct}% of price ({rupees(margin)} per unit); weekly contribution at "
            f"medium demand {rupees(weekly)} (assumption: {share}% of capacity sold)"
        ),
    )


def budget_fit(result: FeasibilityResult) -> DimensionScore:
    check = result.budget_check
    budget = check.budget.value
    total = check.total_required.value
    wc = check.working_capital.value if check.working_capital else Decimal(0)
    breakdown = (
        f"startup {rupees(check.startup_cost.value)} + working capital {rupees(wc)} "
        f"(assumption: first week's variable cost at full capacity) = {rupees(total)}"
    )
    if not check.within_budget:
        return DimensionScore(
            dimension="budget",
            score=0,
            reason=(
                f"over budget: {breakdown} against budget {rupees(budget)}, "
                f"short by {rupees(check.shortfall.value)}"
            ),
        )
    headroom = check.headroom.value
    share = headroom / budget if budget > 0 else Decimal(0)
    score = _clamp(WITHIN_BUDGET_FLOOR + _floor_int(share * HUNDRED))
    return DimensionScore(
        dimension="budget",
        score=score,
        reason=f"within budget: {breakdown} against budget {rupees(budget)}, "
        f"headroom {rupees(headroom)}",
    )


def capacity_fit(
    profile: ConstraintProfile, option: StrategyOption, result: FeasibilityResult
) -> DimensionScore:
    weekly_units = result.weekly_capacity.value
    if weekly_units == 0:
        return DimensionScore(
            dimension="capacity",
            score=0,
            reason="no weekly capacity: zero units per day or zero days per week",
        )
    minutes = option.minutes_per_unit
    available = profile.hours_per_week
    needed = Decimal(minutes.value * weekly_units) / MINUTES_PER_HOUR
    detail = (
        f"needs {needed:.1f} h/week ({minutes.value} min x {weekly_units} units, "
        f"{_label(minutes.source)}) against {available.value} h/week available "
        f"({_label(available.source)})"
    )
    if needed <= available.value:
        return DimensionScore(dimension="capacity", score=100, reason=f"fits: {detail}")
    score = _clamp(_floor_int(Decimal(available.value) / needed * HUNDRED))
    return DimensionScore(dimension="capacity", score=score, reason=f"short on time: {detail}")


def _normalise(items: list[str]) -> list[str]:
    """Trim, lowercase and de-duplicate, keeping first-seen order."""
    return list(dict.fromkeys(item.strip().lower() for item in items if item.strip()))


def missing_items(required: list[str], have: list[str]) -> list[str]:
    owned = set(_normalise(have))
    return [item for item in _normalise(required) if item not in owned]


def skill_equipment_fit(profile: ConstraintProfile, option: StrategyOption) -> DimensionScore:
    required = len(_normalise(option.required_skills)) + len(_normalise(option.required_equipment))
    if required == 0:
        return DimensionScore(
            dimension="skill_equipment", score=100, reason="nothing required, so nothing missing"
        )
    missing_skills = missing_items(option.required_skills, profile.skills)
    missing_equipment = missing_items(option.required_equipment, profile.equipment)
    missing = len(missing_skills) + len(missing_equipment)
    score = _floor_int(Decimal(required - missing) / Decimal(required) * HUNDRED)
    if missing == 0:
        reason = f"all {required} required skills and equipment present"
    else:
        parts = []
        if missing_skills:
            parts.append(f"missing skills: {', '.join(missing_skills)}")
        if missing_equipment:
            parts.append(f"missing equipment: {', '.join(missing_equipment)}")
        reason = f"{required - missing} of {required} present; " + "; ".join(parts)
    return DimensionScore(dimension="skill_equipment", score=score, reason=reason)


def market_signal_fit(
    option: StrategyOption, opportunity: Opportunity | None, today: date
) -> DimensionScore:
    if opportunity is None:
        # No evidence is not evidence against: the original idea and an alternative the owner
        # chose to leave unlinked both get the same neutral score, and neither is a finding.
        what = "the original idea" if option.is_original else "this option"
        return DimensionScore(
            dimension="market_signal",
            score=NO_EVIDENCE_SCORE,
            reason=f"no market evidence for {what}; neutral score",
        )
    if opportunity.direction == "against":
        # Evidence against an option gives it no market support, however strong or verified.
        return DimensionScore(
            dimension="market_signal",
            score=0,
            reason=(
                f"evidence from {opportunity.source_name} argues against this option, "
                "so no market support"
            ),
        )
    if opportunity.has_passed(today):
        return DimensionScore(
            dimension="market_signal",
            score=0,
            reason=(
                f"event passed: evidence from {opportunity.source_name} "
                f"was on {opportunity.event_date}"
            ),
        )
    score = SIGNAL_POINTS[opportunity.signal_strength]
    notes = [f"evidence from {opportunity.source_name}: {opportunity.signal_strength} signal"]
    notes.append("evergreen" if opportunity.is_evergreen else f"event on {opportunity.event_date}")
    notes.append(opportunity.verification_status.replace("_", " "))
    if opportunity.verification_status != "verified":
        score -= UNVERIFIED_DEDUCTION
        notes.append(f"minus {UNVERIFIED_DEDUCTION} for weaker verification")
    return DimensionScore(dimension="market_signal", score=_clamp(score), reason=", ".join(notes))
