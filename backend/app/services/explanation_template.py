"""The standard explanation used when Claude is off, capped or fails. Deterministic, no AI.

Every sentence is built from the engine's own figures, and the result must pass the same
post-check as Claude's text (a test runs it for every seeded scenario).
"""

from app.services.analyze_models import AnalyzeResponse
from app.services.explanation_facts import is_placeholder, linked_evidence, recommended_option
from app.services.scoring import rupees


def _caveat(analysis: AnalyzeResponse) -> str:
    if any(is_placeholder(e.id) for e in analysis.evidence):
        return (
            "Some inputs are assumptions and some market entries are placeholders, "
            "so treat this as a guide, not a promise of profit."
        )
    if any(e.verification_status != "verified" for e in analysis.evidence):
        return (
            "Some inputs are assumptions and some market sources are cited but not yet verified, "
            "so treat this as a guide, not a promise of profit."
        )
    return "Some inputs are assumptions, so treat this as a guide, not a promise of profit."


def _nothing_viable(analysis: AnalyzeResponse) -> list[str]:
    worst = [
        f"{s.title}: {', '.join(s.viability_issues) or 'not viable'}"
        for s in analysis.ranking.ranked[:2]
    ]  # noqa: E501
    return [
        "The engine found no viable option with your current budget, time and skills.",
        "Here is why: " + "; ".join(worst) + ".",
        "Nothing is recommended, so try a lower-cost option, a higher price or more time, "
        "and run the check again.",
        _caveat(analysis),
    ]


def templated_summary(analysis: AnalyzeResponse) -> str:
    ranking = analysis.ranking
    rec = recommended_option(analysis)
    score = next((s for s in ranking.ranked if s.option_id == ranking.recommended_id), None)
    if rec is None or score is None:
        return " ".join(_nothing_viable(analysis))

    check = rec.feasibility.budget_check
    margin = rec.feasibility.contribution_margin.value
    pct = rec.feasibility.contribution_margin_pct.value
    if rec.is_suggested:
        first = (
            f"The engine recommends switching to {rec.title}, a suggestion from LaunchWise and "
            f"not your own idea, which scored {score.total} out of 100."
        )
    elif ranking.keep_original:
        first = (
            f"The engine recommends keeping your original idea, {rec.title}, "
            f"which scored {score.total} out of 100."
        )
    else:
        first = (
            f"The engine recommends switching to {rec.title}, "
            f"which scored {score.total} out of 100."
        )
    margin_part = f"Each sale leaves a margin of {rupees(margin)}"
    if pct is not None:
        margin_part += f" ({pct}% of the price)"
    verdict = "which is within" if check.within_budget else "which is over"
    money = (
        f"{margin_part}, and getting started needs {rupees(check.total_required.value)}, "
        f"{verdict} your budget of {rupees(analysis.profile.budget)}."
    )
    sentences = [first, money]

    against = linked_evidence(analysis, rec.option_id)
    if against is not None and against.direction == "against":
        sentences.append(
            f"Market evidence from {against.source_name} argues against this option, so the "
            "recommendation rests on your numbers alone."
        )
    other = next((s for s in ranking.ranked if s.option_id != rec.option_id), None)
    if other is not None:
        label = "Your original idea" if other.is_original else "The next best option"
        other_evidence = linked_evidence(analysis, other.option_id)
        tail = (
            f", and market evidence from {other_evidence.source_name} argues against it"
            if other_evidence is not None and other_evidence.direction == "against"
            else ""
        )
        sentences.append(f"{label}, {other.title}, scored {other.total}{tail}.")
    if analysis.market_coverage == "none":
        sentences.append(
            f"No market data covers {analysis.profile.location}, so this checks feasibility "
            "only and suggests no pivots."
        )
    sentences.append(_caveat(analysis))
    return " ".join(sentences)
