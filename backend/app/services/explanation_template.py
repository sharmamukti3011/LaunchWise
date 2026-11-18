"""The standard explanation used when Claude is off, capped or fails. Deterministic, no AI.

Every sentence is built from the engine's own figures, and the result must pass the same
post-check as Claude's text (a test runs it for every seeded scenario).
"""

from app.services.analyze_models import AnalyzeResponse
from app.services.explanation_facts import is_placeholder, recommended_option
from app.services.scoring import rupees


def _caveat(analysis: AnalyzeResponse) -> str:
    placeholders = any(is_placeholder(e.id, e.verification_status) for e in analysis.evidence)
    if placeholders:
        return (
            "Some inputs are assumptions and the market entries are unverified placeholders, "
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
    if ranking.keep_original:
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

    other = next((s for s in ranking.ranked if s.option_id != rec.option_id), None)
    if other is not None:
        label = "Your original idea" if other.is_original else "The next best option"
        sentences.append(f"{label}, {other.title}, scored {other.total}.")
    if analysis.market_coverage == "none":
        sentences.append(
            f"No market data covers {analysis.profile.location}, so this checks feasibility "
            "only and suggests no pivots."
        )
    sentences.append(_caveat(analysis))
    return " ".join(sentences)
