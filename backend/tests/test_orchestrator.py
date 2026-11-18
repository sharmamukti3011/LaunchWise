"""The Explain call: Claude explains the engine's result, the engine's numbers stay the truth."""

import json
import logging
from typing import Any

import pytest

from app.services.call_budget import CallBudget
from app.services.explanation_check import validate_summary
from app.services.explanation_template import templated_summary
from app.services.orchestrator import ClaudeUnavailable, ExplainService
from tests.explain_helpers import GOOD, IDS, analysis_for, reply
from tests.fakes import FakeClaude

KEY = "203.0.113.7"
LEAD = "The engine recommends Custom celebration cakes."


def service(
    claude: FakeClaude | None, per_key: int = 20, total: int = 500, max_keys: int = 100
) -> ExplainService:
    return ExplainService(claude, CallBudget(per_key=per_key, total=total, max_keys=max_keys))


def explain(svc: ExplainService, scenario: str = "pune-pivot", key: str = KEY) -> Any:
    return svc.explain(analysis_for(scenario), key)


# ---- the happy path ---------------------------------------------------------------------------


def test_a_valid_reply_is_returned_as_claudes_explanation() -> None:
    fake = FakeClaude(reply(GOOD))
    result = explain(service(fake))
    assert result.source == "claude" and result.fallback_reason is None
    assert result.summary == GOOD
    assert len(fake.calls) == 1


def test_the_request_gives_claude_the_facts_and_the_rules_and_no_model_name() -> None:
    fake = FakeClaude(reply(GOOD))
    explain(service(fake))
    system, messages, max_tokens = fake.calls[0]
    assert "engine has already made every decision" in system
    assert "3 to 5" in system and "JSON" in system and "₹" in system
    assert "instructions" in system  # the facts are data, not instructions
    assert len(messages) == 1 and messages[0]["role"] == "user"
    facts = json.loads(messages[0]["content"].split("FACTS:\n", 1)[1])
    assert facts["recommended"]["title"] == "Custom celebration cakes"
    assert facts["keep_original"] is False
    assert any(e["id"] == "TODO-VERIFY-PUNE-001" and e["placeholder"] for e in facts["evidence"])
    assert max_tokens <= 8000
    assert "$" not in messages[0]["content"] + system  # rupees everywhere


def test_the_facts_carry_the_engines_figures_with_their_source_tags() -> None:
    fake = FakeClaude(reply(GOOD))
    explain(service(fake))
    facts = json.loads(fake.calls[0][1][0]["content"].split("FACTS:\n", 1)[1])
    figures = {f["label"]: f for f in facts["recommended"]["figures"]}
    assert figures["Margin per unit"]["value"] == "₹900.00"
    assert figures["Margin per unit"]["source"] == "derived"


# ---- retry once, then fall back ---------------------------------------------------------------


def test_invalid_output_is_retried_once_with_the_reason_and_can_then_succeed() -> None:
    fake = FakeClaude("not json at all", reply(GOOD))
    result = explain(service(fake))
    assert result.source == "claude" and len(fake.calls) == 2
    retry_messages = fake.calls[1][1]
    assert [m["role"] for m in retry_messages] == ["user", "assistant", "user"]
    assert "rejected" in retry_messages[2]["content"]


def test_two_invalid_replies_fall_back_to_the_template_and_never_call_a_third_time() -> None:
    fake = FakeClaude("nope", "still nope")
    result = explain(service(fake))
    assert result.source == "template" and result.fallback_reason == "invalid"
    assert len(fake.calls) == 2
    assert validate_summary(result.summary, analysis_for()) is None


def test_an_unavailable_claude_falls_back_at_once_without_a_retry() -> None:
    fake = FakeClaude(ClaudeUnavailable("down"))
    result = explain(service(fake))
    assert result.source == "template" and result.fallback_reason == "unavailable"
    assert len(fake.calls) == 1


def test_no_client_means_the_template_and_no_calls() -> None:
    result = explain(service(None))
    assert result.source == "template" and result.fallback_reason == "not_configured"


# ---- the post-check ---------------------------------------------------------------------------


def check(summary: str, scenario: str = "pune-pivot") -> str | None:
    return validate_summary(summary, analysis_for(scenario))


def test_the_good_explanation_passes() -> None:
    assert check(GOOD) is None


@pytest.mark.parametrize(
    "variant",
    [
        "₹900", "₹900.00", "900", "64.29%", "₹10,000", "83.25", "100", "₹7,000.00", "₹3,000.00",
    ],
)  # fmt: skip
def test_figures_in_any_spelling_of_a_response_number_are_allowed(variant: str) -> None:
    text = f"The engine recommends Custom celebration cakes. It leaves {variant} here. Be careful."
    assert check(text) is None


@pytest.mark.parametrize(
    "invented",
    ["₹1,23,456", "47%", "7.5", "₹901", "1500", "99.99"],
)
def test_a_figure_that_is_not_in_the_response_is_rejected(invented: str) -> None:
    text = f"{LEAD} It could earn {invented} a month. Be careful."
    problem = check(text)
    assert problem is not None and "not in the facts" in problem


@pytest.mark.parametrize("word", ["thousand", "lakh", "seventeen", "thirteen", "million", "crore"])
def test_spelled_out_numbers_that_are_not_in_the_response_are_rejected(word: str) -> None:
    text = f"{LEAD} It could earn a {word} soon. Be careful."
    problem = check(text)
    assert problem is not None and "not in the facts" in problem


def test_a_dataset_id_that_is_not_in_the_response_is_rejected() -> None:
    text = GOOD.replace("TODO-VERIFY-PUNE-001", "TODO-VERIFY-PUNE-009")
    problem = check(text)
    assert problem is not None and "dataset ID" in problem


def test_an_id_digit_is_not_mistaken_for_a_free_standing_number() -> None:
    assert check(GOOD) is None  # "001" belongs to the ID, not a number of its own


def test_a_wrong_recommended_option_is_rejected() -> None:
    text = GOOD.replace("Custom celebration cakes", "Open a small shop")
    problem = check(text)
    assert problem is not None and "Custom celebration cakes" in problem


@pytest.mark.parametrize(
    "summary",
    [
        "One sentence only.",
        "One. Two. ",
        "The engine recommends Custom celebration cakes. A. B. C. D. E.",
    ],
)
def test_the_sentence_count_must_be_three_to_five(summary: str) -> None:
    problem = check(summary)
    assert problem is not None and "3 to 5 sentences" in problem


@pytest.mark.parametrize(
    "bad",
    [
        "<b>bold</b>",
        "<script>alert(1)</script>",
        "[link](http://x)",
        "line\x00break",
        "```code```",
    ],
)
def test_markup_and_control_characters_are_rejected(bad: str) -> None:
    text = f"The engine recommends Custom celebration cakes. Use {bad} here. Be careful."
    problem = check(text)
    assert problem is not None and "markup" in problem


@pytest.mark.parametrize("phrase", ["guaranteed profit", "risk-free", "You will make money"])
def test_promises_of_profit_are_rejected(phrase: str) -> None:
    text = f"The engine recommends Custom celebration cakes. This is {phrase}. Be careful."
    problem = check(text)
    assert problem is not None and "promise" in problem


def test_when_nothing_is_viable_an_explanation_that_says_so_passes() -> None:
    ok = (
        "The engine found no viable option within your budget. "
        "Everyday cakes has no positive margin and Premium wedding cakes is over budget. "
        "Adjust your prices or budget and run it again. Nothing here is a promise of profit."
    )
    assert check(ok, "pune-nothing-viable") is None


@pytest.mark.parametrize(
    "raw",
    [
        "[]",
        '{"summary": 5}',
        '{"summary": "x", "extra": 1}',
        '{"text": "x"}',
        "",
        "```json\n{not valid}\n```",
    ],
)
def test_output_that_is_not_the_expected_json_object_is_invalid(raw: str) -> None:
    result = explain(service(FakeClaude(raw, raw)))
    assert result.source == "template" and result.fallback_reason == "invalid"


def test_a_json_code_fence_is_tolerated() -> None:
    fenced = "```json\n" + reply(GOOD) + "\n```"
    result = explain(service(FakeClaude(fenced)))
    assert result.source == "claude" and result.summary == GOOD


# ---- call caps --------------------------------------------------------------------------------


def test_the_per_session_cap_stops_calls_and_falls_back() -> None:
    fake = FakeClaude(reply(GOOD), reply(GOOD))
    svc = service(fake, per_key=2)
    assert explain(svc).source == "claude"
    assert explain(svc).source == "claude"
    third = explain(svc)
    assert third.source == "template" and third.fallback_reason == "budget"
    assert len(fake.calls) == 2


def test_the_per_session_cap_is_per_visitor() -> None:
    fake = FakeClaude(reply(GOOD), reply(GOOD))
    svc = service(fake, per_key=1)
    assert explain(svc, key="a").source == "claude"
    assert explain(svc, key="a").fallback_reason == "budget"
    assert explain(svc, key="b").source == "claude"


def test_the_global_cap_applies_across_visitors() -> None:
    fake = FakeClaude(reply(GOOD))
    svc = service(fake, per_key=10, total=1)
    assert explain(svc, key="a").source == "claude"
    assert explain(svc, key="b").fallback_reason == "budget"


def test_a_retry_spends_budget_too() -> None:
    fake = FakeClaude("bad", reply(GOOD))
    result = explain(service(fake, per_key=1))
    assert result.source == "template" and result.fallback_reason == "budget"
    assert len(fake.calls) == 1


def test_a_refused_per_visitor_reservation_does_not_burn_the_global_budget() -> None:
    budget = CallBudget(per_key=1, total=2, max_keys=10)
    assert budget.reserve("a") and not budget.reserve("a")
    assert budget.reserve("b")  # the refused hit on "a" did not use a global call
    assert not budget.reserve("c")


def test_the_budget_forgets_old_visitors_instead_of_growing_forever() -> None:
    budget = CallBudget(per_key=1, total=1000, max_keys=3)
    for i in range(10):
        budget.reserve(f"k{i}")
    assert len(budget) <= 3


# ---- the templated explanation ----------------------------------------------------------------


@pytest.mark.parametrize("scenario", IDS)
def test_the_template_passes_the_same_post_check_for_every_scenario(scenario: str) -> None:
    analysis = analysis_for(scenario)
    summary = templated_summary(analysis)
    assert validate_summary(summary, analysis) is None, summary
    assert "$" not in summary


def test_the_template_names_the_recommendation_or_says_none_is_viable() -> None:
    assert "Custom celebration cakes" in templated_summary(analysis_for("pune-pivot"))
    keep = templated_summary(analysis_for("pune-keep-original"))
    assert "keeping" in keep.lower() and "Everyday cakes" in keep
    none = templated_summary(analysis_for("pune-nothing-viable"))
    assert "no viable option" in none.lower()


def test_the_template_is_deterministic() -> None:
    a = analysis_for("pune-pivot")
    assert templated_summary(a) == templated_summary(a)


# ---- logging ----------------------------------------------------------------------------------


def test_outcomes_are_logged_without_the_text_or_the_visitor(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.INFO, logger="launchwise.explain"):
        explain(service(FakeClaude(reply(GOOD))))
        explain(service(None))
    text = " ".join(r.getMessage() for r in caplog.records)
    assert (
        "explain outcome=claude" in text
        and "explain outcome=template reason=not_configured" in text
    )
    assert KEY not in text and "celebration" not in text and "₹" not in text
