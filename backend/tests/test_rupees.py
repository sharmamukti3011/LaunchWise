"""Rupee display: whole rupees without .00, paise only when a value is not whole."""

import json
import re
from decimal import Decimal

import pytest

from app.services.analyze_models import AnalyzeRequest
from app.services.analyze_service import AnalyzeService
from app.services.demo_catalog import load_demo_catalog
from app.services.explanation_check import validate_summary
from app.services.explanation_facts import build_facts
from app.services.explanation_template import templated_summary
from app.services.market_data import load_dataset
from app.services.scoring import rupees
from tests.explain_helpers import GOOD, IDS, analysis_for
from tests.fakes import FakeClock

D = Decimal
WHOLE_WITH_PAISE = re.compile(r"₹[\d,]+\.00(?!\d)")


@pytest.mark.parametrize(
    ("amount", "shown"),
    [
        ("10000", "₹10,000"),
        ("10000.00", "₹10,000"),
        ("0", "₹0"),
        ("0.00", "₹0"),
        ("900.50", "₹900.50"),
        ("0.5", "₹0.50"),
        ("999.995", "₹1,000"),  # rounds to paise first, then checks whether it is whole
        ("899.994", "₹899.99"),
        ("125000", "₹1,25,000"),  # Indian grouping, the same as the screen
        ("1234567.5", "₹12,34,567.50"),
        ("100", "₹100"),
        ("1000", "₹1,000"),
    ],
)
def test_whole_rupees_have_no_paise_and_others_keep_them(amount: str, shown: str) -> None:
    assert rupees(D(amount)) == shown


def test_a_negative_amount_keeps_its_sign() -> None:
    assert rupees(D("-1500.00")) == "-₹1,500"


@pytest.mark.parametrize("scenario", IDS)
def test_nothing_the_owner_reads_shows_a_whole_rupee_amount_with_double_zero(
    scenario: str,
) -> None:
    analysis = analysis_for(scenario)
    texts = [c.message for c in analysis.ranking.caveats]
    texts += [analysis.market_message, *(s.title for s in analysis.steps)]
    for score in analysis.ranking.ranked:
        texts += [*score.viability_issues, *(s.reason for s in score.scores)]
    texts += [templated_summary(analysis), json.dumps(build_facts(analysis), ensure_ascii=False)]
    for text in texts:
        assert not WHOLE_WITH_PAISE.search(text), text


def test_the_lead_scenario_reads_in_whole_rupees() -> None:
    analysis = analysis_for("pune-pivot")
    summary = templated_summary(analysis)
    assert "₹900 (64.29% of the price)" in summary
    assert "₹7,000" in summary and "₹10,000." in summary
    assert "Checked constraints: budget ₹10,000," in analysis.steps[0].title
    facts = build_facts(analysis)
    figures = {f["label"]: f["value"] for f in facts["recommended"]["figures"]}
    assert figures["Margin per unit"] == "₹900" and facts["budget"] == "₹10,000"


def test_paise_are_kept_when_a_value_is_not_whole() -> None:
    request = load_demo_catalog().request("pune-pivot")
    assert request is not None
    body = request.model_dump(mode="json")
    body["options"][1]["price"] = "1400.50"  # the custom cakes: margin becomes 900.50
    analysis = AnalyzeService(load_dataset(), FakeClock()).analyze(
        AnalyzeRequest.model_validate(body)
    )
    assert "₹900.50" in templated_summary(analysis)
    assert any("₹900.50" in s.title for s in analysis.steps)


# ---- the post-check accepts both spellings of the same amount ---------------------------------


@pytest.mark.parametrize("form", ["₹7,000", "₹7,000.00", "7000", "₹7000.00", "7,000"])
def test_the_check_accepts_every_spelling_of_the_same_amount(form: str) -> None:
    analysis = analysis_for("pune-pivot")
    text = (
        "The engine recommends Custom celebration cakes, which scored 90.00 out of 100. "
        f"Getting started needs {form} in total. Treat this as a guide, not a promise of profit."
    )
    assert validate_summary(text, analysis) is None


def test_the_check_still_rejects_a_different_amount_in_either_form() -> None:
    analysis = analysis_for("pune-pivot")
    for form in ("₹7,001", "₹7,001.00"):
        text = GOOD.replace("₹900,", f"{form},")
        problem = validate_summary(text, analysis)
        assert problem is not None and "not in the facts" in problem


def test_good_explanations_pass_in_both_forms() -> None:
    analysis = analysis_for("pune-pivot")
    assert validate_summary(GOOD, analysis) is None
    with_paise = GOOD.replace("₹900,", "₹900.00,").replace("₹10,000.", "₹10,000.00.")
    assert with_paise != GOOD and validate_summary(with_paise, analysis) is None
