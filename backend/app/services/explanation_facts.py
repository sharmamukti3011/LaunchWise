"""The facts Claude is allowed to use, taken from the engine's response and nothing else.

Money is formatted here, once, so the template and the prompt show identical figures.
"""

from typing import Any

from app.services.analyze_models import AnalyzeResponse, OptionAnalysis
from app.services.scoring import rupees
from app.services.strategy_models import OptionScore


def option_by_id(analysis: AnalyzeResponse, option_id: str | None) -> OptionAnalysis | None:
    return next((o for o in analysis.options if o.option_id == option_id), None)


def recommended_option(analysis: AnalyzeResponse) -> OptionAnalysis | None:
    return option_by_id(analysis, analysis.ranking.recommended_id)


def is_placeholder(entry_id: str, status: str) -> bool:
    return status == "unverified_sample" or entry_id.upper().startswith("TODO-VERIFY")


def figures(option: OptionAnalysis) -> list[dict[str, str]]:
    f = option.feasibility
    check = f.budget_check
    rows = [
        ("Startup cost", rupees(f.startup_cost.value), f.startup_cost.source),
        ("Margin per unit", rupees(f.contribution_margin.value), f.contribution_margin.source),
    ]
    if f.contribution_margin_pct.value is not None:
        pct = f"{f.contribution_margin_pct.value}%"
        rows.append(("Margin", pct, f.contribution_margin_pct.source))
    rows.append(("Weekly capacity (units)", str(f.weekly_capacity.value), f.weekly_capacity.source))
    rows.append(
        ("Total needed up front", rupees(check.total_required.value), check.total_required.source)
    )  # noqa: E501
    if check.within_budget:
        rows.append(("Left in budget", rupees(check.headroom.value), check.headroom.source))
    else:
        rows.append(("Short of budget by", rupees(check.shortfall.value), check.shortfall.source))
    return [{"label": a, "value": b, "source": c} for a, b, c in rows]


def _ranked_entry(score: OptionScore) -> dict[str, Any]:
    return {
        "title": score.title,
        "is_original": score.is_original,
        "total": str(score.total),
        "viable": score.viable,
        "issues": score.viability_issues,
        "reasons": {s.dimension: s.reason for s in score.scores},
    }


def build_facts(analysis: AnalyzeResponse) -> dict[str, Any]:
    ranking = analysis.ranking
    rec = recommended_option(analysis)
    rec_score = next((s for s in ranking.ranked if s.option_id == ranking.recommended_id), None)
    recommended: dict[str, Any] | None = None
    if rec is not None and rec_score is not None:
        recommended = {
            "title": rec.title,
            "total": str(rec_score.total),
            "is_original": rec.is_original,
            "figures": figures(rec),
        }
    return {
        "location": analysis.profile.location,
        "category": analysis.category,
        "budget": rupees(analysis.profile.budget),
        "market_coverage": analysis.market_coverage,
        "market_message": analysis.market_message,
        "keep_original": ranking.keep_original,
        "recommended": recommended,
        "ranked": [_ranked_entry(s) for s in ranking.ranked],
        "caveats": [c.message for c in ranking.caveats],
        "evidence": [
            {
                "id": e.id,
                "title": e.title,
                "status": e.verification_status,
                "signal": e.signal_strength,
                "placeholder": is_placeholder(e.id, e.verification_status),
            }
            for e in analysis.evidence
        ],
    }
