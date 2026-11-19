"""The profit-promise check rejects promises, but not sentences that deny one."""

import pytest

from app.services.explanation_check import validate_summary
from tests.explain_helpers import analysis_for

LEAD = "The engine recommends Custom celebration cakes, which scored 90.00 out of 100. "


def check(middle: str) -> str | None:
    return validate_summary(f"{LEAD}{middle} Treat this as a guide.", analysis_for("pune-pivot"))


@pytest.mark.parametrize(
    "middle",
    [
        "Nothing is guaranteed.",
        "None of this is guaranteed to happen, so treat it with care.",
        "These results are not guaranteed.",
        "There is no guarantee of profit.",
        "We cannot guarantee any result.",
        "We can't guarantee success.",
        "This does not guarantee success.",
        "That isn't guaranteed either.",
        "Results are never guaranteed.",
        "It is not risk-free.",
        "This is not a guarantee.",
        "It makes no guarantee about demand.",
        "It is offered without any guarantee.",
        "Nothing is guaranteed, and the real results could be quite different.",
    ],
)
def test_a_sentence_that_denies_a_promise_is_accepted(middle: str) -> None:
    assert check(middle) is None


@pytest.mark.parametrize(
    "middle",
    [
        "This is guaranteed profit.",
        "We guarantee results.",
        "It is a guarantee of success.",
        "This plan is risk-free.",
        "You will make money.",
        "There is no risk.",
        "You cannot lose.",
        "You are sure to profit.",
        "It is certain to work.",
        "It is guaranteed to pay back.",
    ],
)
def test_a_real_promise_is_still_rejected(middle: str) -> None:
    problem = check(middle)
    assert problem is not None and "promise" in problem


def test_a_denial_far_from_the_promise_does_not_excuse_it() -> None:
    problem = check("Not everything here is certain, but for you this is guaranteed profit.")
    assert problem is not None and "promise" in problem


def test_a_denial_in_another_sentence_does_not_excuse_it() -> None:
    problem = check("Nothing is certain. This is guaranteed profit.")
    assert problem is not None and "promise" in problem


def test_one_promise_among_denials_is_still_caught() -> None:
    problem = check("Nothing is guaranteed. It is risk-free.")
    assert problem is not None and "promise" in problem


def test_the_curly_apostrophe_counts_as_a_denial() -> None:
    assert check("That isn’t guaranteed.") is None


# The reply Claude actually gave for a user-submitted idea, which the old check wrongly rejected.
REAL_REPLY = (
    "The engine recommends Custom celebration cakes over your original idea, Everyday cakes. "
    "It has a margin of ₹900 per unit, which is 64.29%, while Everyday cakes earn only ₹50 per "
    "unit, or 10.00%. The startup cost is ₹4,000, and the total needed up front is ₹7,000 against "
    "your budget of ₹10,000, which leaves ₹3,000 in the budget. Market evidence from YourStory "
    "(HerStory) supports this option, and it is marked verified with a medium signal, while there "
    "is no market evidence for Everyday cakes. One caveat: the 20 weekly hours available, the 60 "
    "minutes per item, the ₹3,000 working capital reserve and the level of demand are all "
    "assumptions, not facts from you, so the real results could be quite different and nothing "
    "is guaranteed."
)


def test_the_real_reply_that_was_wrongly_rejected_now_passes() -> None:
    from app.services.analyze_models import AnalyzeRequest
    from app.services.analyze_service import AnalyzeService
    from app.services.market_data import load_dataset
    from tests.fakes import FakeClock

    body = {
        "profile": {
            "budget": "10000", "units_per_day": 3, "days_per_week": 2,
            "skills": ["baking"], "equipment": ["oven"], "location": "Pune",
        },
        "category": "home bakery",
        "options": [
            {"id": "original", "title": "Everyday cakes", "is_original": True, "price": "500",
             "variable_cost_per_unit": "450", "fixed_startup_costs": "3000"},
            {"id": "alternative", "title": "Custom celebration cakes", "is_original": False,
             "price": "1400", "variable_cost_per_unit": "500", "fixed_startup_costs": "4000",
             "opportunity_id": "PUNE-001"},
        ],
    }  # fmt: skip
    analysis = AnalyzeService(load_dataset(), FakeClock()).analyze(
        AnalyzeRequest.model_validate(body)
    )
    assert validate_summary(REAL_REPLY, analysis) is None


def test_the_numbers_and_sources_stay_strict() -> None:
    # The promise fix loosens nothing else: an invented figure or source is still refused.
    assert "not in the facts" in (
        check("It could earn ₹9,999 a month. Nothing is guaranteed.") or ""
    )
    assert "not in the facts" in (
        check("Evidence from Swiggy backs it. Nothing is guaranteed.") or ""
    )
