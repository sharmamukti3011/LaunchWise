"""Explanations refer to evidence by source name, never by dataset ID, and only real sources."""

import json
import re

import pytest

from app.services.explanation_check import validate_summary
from app.services.explanation_facts import build_facts
from app.services.explanation_template import templated_summary
from app.services.orchestrator import SYSTEM_PROMPT
from tests.explain_helpers import GOOD, IDS, analysis_for

ID_LIKE = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b")
LEAD = "The engine recommends Custom celebration cakes, which scored 90.00 out of 100. "
TAIL = " Treat this as a guide, not a promise of profit."


def check(middle: str, scenario: str = "pune-pivot") -> str | None:
    return validate_summary(LEAD + middle + TAIL, analysis_for(scenario))


# ---- the prompt and the facts -----------------------------------------------------------------


def test_the_prompt_asks_for_source_names_and_forbids_dataset_ids() -> None:
    assert "source name" in SYSTEM_PROMPT and "market evidence from" in SYSTEM_PROMPT
    assert "Never use dataset IDs" in SYSTEM_PROMPT
    assert "dataset IDs that appear" not in SYSTEM_PROMPT  # the old rule is gone


@pytest.mark.parametrize("scenario", IDS)
def test_the_facts_sent_to_claude_contain_no_dataset_ids(scenario: str) -> None:
    text = json.dumps(build_facts(analysis_for(scenario)), ensure_ascii=False)
    assert not ID_LIKE.search(text), ID_LIKE.search(text)


def test_the_facts_name_each_source_once_per_entry() -> None:
    facts = build_facts(analysis_for("pune-pivot"))
    assert {e["source"] for e in facts["evidence"]} == {"YourStory (HerStory)", "Housing.com"}
    assert all("id" not in e for e in facts["evidence"])


# ---- the post-check: sources must belong to the response --------------------------------------


@pytest.mark.parametrize(
    "middle",
    [
        "Market evidence from YourStory (HerStory) shows a clear premium for occasion cakes.",
        # A whole-word prefix of "YourStory (HerStory)" is accepted.
        "Market evidence from YourStory shows a clear premium for occasion cakes.",
        "A shopfront looks unrealistic because evidence from Housing.com argues against it.",
        "Data from Housing.com and evidence from YourStory (HerStory) both matter.",
        "According to Housing.com, rents are far above your budget, which argues against it.",
        "It rests on your own numbers and not on any outside source.",
    ],
)
def test_sources_that_belong_to_the_response_are_accepted(middle: str) -> None:
    assert check(middle) is None


@pytest.mark.parametrize(
    "middle",
    [
        "Market evidence from Swiggy shows strong festive demand.",
        # Business Today is in the dataset, but not in this response.
        "According to Business Today, Pune is a top city for festive orders.",
        "Data from Bakeway suggests an established marketplace.",
        "A survey by HomeBakers.co.in found high earnings.",
        "Evidence from YourStory Pune bakers shows demand.",  # extra words after a real name
    ],
)
def test_a_source_that_is_not_in_the_response_is_rejected(middle: str) -> None:
    problem = check(middle)
    assert problem is not None and "not in the facts" in problem


def test_the_rejection_names_the_offending_source_so_claude_can_fix_it() -> None:
    problem = check("Market evidence from Swiggy shows strong demand.")
    assert problem is not None and "Swiggy" in problem


@pytest.mark.parametrize("dataset_id", ["PUNE-001", "PUNE-003", "PUNE-009", "TODO-VERIFY-PUNE-001"])
def test_any_dataset_id_is_rejected_and_the_reason_says_to_name_the_source(dataset_id: str) -> None:
    problem = check(f"Market evidence {dataset_id} shows a premium.")
    assert problem is not None and dataset_id in problem
    assert "name the source" in problem


def test_the_source_check_is_per_response_not_per_dataset() -> None:
    # Housing.com is a real dataset source, but the keep-original scenario never links it.
    analysis = analysis_for("pune-keep-original")
    text = (
        "The engine recommends keeping your original idea, Everyday cakes (original idea), "
        "which scored 85.10 out of 100. Evidence from Housing.com matters here. "
        "Treat this as a guide, not a promise of profit."
    )
    problem = validate_summary(text, analysis)
    assert problem is not None and "Housing.com" in problem


def test_good_still_passes_with_its_source_name() -> None:
    assert "YourStory (HerStory)" in GOOD and "PUNE" not in GOOD
    assert validate_summary(GOOD, analysis_for("pune-pivot")) is None


# ---- the template -----------------------------------------------------------------------------


@pytest.mark.parametrize("scenario", IDS)
def test_the_template_never_shows_a_dataset_id_and_still_passes_the_check(scenario: str) -> None:
    analysis = analysis_for(scenario)
    text = templated_summary(analysis)
    assert not ID_LIKE.search(text)
    assert validate_summary(text, analysis) is None


# ---- the engine's own caveats -----------------------------------------------------------------


@pytest.mark.parametrize("scenario", IDS)
def test_the_engine_caveat_messages_show_no_dataset_ids(scenario: str) -> None:
    for caveat in analysis_for(scenario).ranking.caveats:
        assert not ID_LIKE.search(caveat.message), caveat.message
