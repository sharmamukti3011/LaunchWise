"""Evidence direction: an entry can support the option it is linked to, or argue against it."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest

from app.services.explanation_check import validate_summary
from app.services.explanation_facts import build_facts
from app.services.explanation_template import templated_summary
from app.services.market_data import DatasetError, load_dataset
from app.services.scoring import market_signal_fit
from tests.explain_helpers import GOOD, analysis_for
from tests.pune_fixtures import TODAY, opportunity, option

D = Decimal


def linked(**overrides: Any) -> Any:
    return option(id="alt", is_original=False, opportunity_id="TEST-FAKE-001", **overrides)


# ---- the model and the data -------------------------------------------------------------------


def test_direction_defaults_to_supports_and_rejects_other_values() -> None:
    assert opportunity().direction == "supports"
    assert opportunity(direction="against").direction == "against"
    with pytest.raises(ValueError):
        opportunity(direction="neutral")


def test_the_shipped_dataset_marks_only_the_shop_rent_entry_as_against() -> None:
    directions = {o.id: o.direction for o in load_dataset().opportunities}
    assert directions == {
        "PUNE-001": "supports",
        "PUNE-002": "supports",
        "PUNE-003": "against",
        "PUNE-004": "supports",
        "PUNE-005": "supports",
    }


def test_a_dataset_entry_with_a_bad_direction_fails_loudly(tmp_path: Path) -> None:
    shipped = Path(__file__).parents[1] / "app" / "data" / "market_opportunities.json"
    data = json.loads(shipped.read_text())
    data["opportunities"][0]["direction"] = "sideways"
    path = tmp_path / "bad.json"
    path.write_text(json.dumps(data))
    with pytest.raises(DatasetError, match="direction"):
        load_dataset(path)


# ---- scoring ----------------------------------------------------------------------------------


def test_against_evidence_gives_a_market_signal_of_zero_however_strong_and_verified() -> None:
    strong = opportunity(signal_strength="high", direction="against")
    score = market_signal_fit(linked(), strong, TODAY)
    assert score.score == 0
    assert "against" in score.reason and "test_fixture" in score.reason


def test_against_evidence_scores_zero_even_when_unverified_or_evergreen() -> None:
    for extra in ({"verification_status": "single_source", "verified_by": None,
                   "verified_on": None}, {"is_evergreen": True, "event_date": None}):  # fmt: skip
        entry = opportunity(direction="against", **extra)
        assert market_signal_fit(linked(), entry, TODAY).score == 0


def test_supporting_evidence_is_scored_as_before() -> None:
    assert market_signal_fit(linked(), opportunity(signal_strength="medium"), TODAY).score == 60


def test_against_evidence_on_the_original_idea_also_scores_zero() -> None:
    original = option(opportunity_id="TEST-FAKE-001")
    entry = opportunity(direction="against")
    assert market_signal_fit(original, entry, TODAY).score == 0


# (The caveat itself is tested in test_compare_strategies.py, next to its helpers.)


# ---- the shipped scenario ---------------------------------------------------------------------


def test_small_shop_in_the_lead_scenario_now_scores_zero_on_the_market() -> None:
    analysis = analysis_for("pune-pivot")
    shop = next(s for s in analysis.ranking.ranked if s.option_id == "small-shop")
    market = next(s for s in shop.scores if s.dimension == "market_signal")
    assert market.score == 0 and "against" in market.reason
    # (100*30 + 0*20 + 100*20 + 66*15 + 0*15) / 100 = 5990 / 100 = 59.90
    assert shop.total == D("59.90")
    assert [s.option_id for s in analysis.ranking.ranked] == [
        "custom-celebration-cakes",
        "original-cakes",
        "small-shop",
    ]
    assert analysis.ranking.recommended_id == "custom-celebration-cakes"


def test_the_response_evidence_carries_the_direction() -> None:
    evidence = {e.id: e.direction for e in analysis_for("pune-pivot").evidence}
    assert evidence == {"PUNE-001": "supports", "PUNE-003": "against"}


# ---- what Claude is told ----------------------------------------------------------------------


def test_the_facts_tell_claude_which_evidence_argues_against_which_option() -> None:
    facts = build_facts(analysis_for("pune-pivot"))
    assert {e["source"]: e["direction"] for e in facts["evidence"]} == {
        "YourStory (HerStory)": "supports",
        "Housing.com": "against",
    }
    shop = next(r for r in facts["ranked"] if r["title"].startswith("Open a small shop"))
    assert shop["market_evidence"] == {"source": "Housing.com", "direction": "against"}


def test_the_system_prompt_says_against_evidence_is_never_support() -> None:
    from app.services.orchestrator import SYSTEM_PROMPT

    assert "against" in SYSTEM_PROMPT and "never describe it as support" in SYSTEM_PROMPT


# ---- the template and the post-check ----------------------------------------------------------


def flip(analysis: Any, evidence_id: str, direction: str = "against") -> Any:
    evidence = [
        e.model_copy(update={"direction": direction}) if e.id == evidence_id else e
        for e in analysis.evidence
    ]
    return analysis.model_copy(update={"evidence": evidence})


def test_the_template_says_so_when_the_recommended_option_has_against_evidence() -> None:
    analysis = flip(analysis_for("pune-pivot"), "PUNE-001")
    text = templated_summary(analysis)
    assert "evidence from YourStory (HerStory) argues against" in text and "PUNE-" not in text
    assert validate_summary(text, analysis) is None


def test_the_template_notes_when_the_next_best_option_has_against_evidence() -> None:
    analysis = flip(analysis_for("pune-keep-original"), "PUNE-004")
    text = templated_summary(analysis)
    assert (
        "Sourdough bread subscription" in text
        and "evidence from YourStory argues against it" in text
    )
    assert validate_summary(text, analysis) is None


def test_the_template_is_unchanged_when_the_recommended_evidence_supports_it() -> None:
    text = templated_summary(analysis_for("pune-pivot"))
    assert "against" not in text.lower()


def test_every_scenario_template_still_passes_the_check() -> None:
    from tests.explain_helpers import IDS

    for scenario in IDS:
        analysis = analysis_for(scenario)
        assert validate_summary(templated_summary(analysis), analysis) is None


def test_the_check_requires_saying_so_when_the_recommended_option_has_against_evidence() -> None:
    analysis = flip(analysis_for("pune-pivot"), "PUNE-001")
    problem = validate_summary(GOOD, analysis)  # GOOD never mentions "against"
    assert problem is not None and "against" in problem


def test_the_check_rejects_calling_against_evidence_support() -> None:
    analysis = analysis_for("pune-pivot")
    text = (
        "The engine recommends Custom celebration cakes, which scored 90.00 out of 100. "
        "The shop idea is backed by evidence from Housing.com, which supports a shopfront. "
        "Treat this as a guide, not a promise of profit."
    )
    problem = validate_summary(text, analysis)
    assert problem is not None and "Housing.com" in problem and "against" in problem


def test_the_check_accepts_describing_against_evidence_correctly() -> None:
    analysis = analysis_for("pune-pivot")
    text = (
        "The engine recommends Custom celebration cakes, which scored 90.00 out of 100. "
        "A shopfront looks unrealistic because evidence from Housing.com argues against it. "
        "Treat this as a guide, not a promise of profit."
    )
    assert validate_summary(text, analysis) is None
