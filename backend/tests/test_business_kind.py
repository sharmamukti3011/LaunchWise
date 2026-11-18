"""Deciding whether a business sells food, so the FSSAI note is shown. Plain keyword rules."""

import pytest

from app.services.analyze_models import AnalyzeRequest
from app.services.analyze_service import AnalyzeService
from app.services.business_kind import is_food_business
from app.services.demo_catalog import load_demo_catalog
from app.services.market_data import load_dataset
from tests.explain_helpers import IDS, analysis_for
from tests.fakes import FakeClock


@pytest.mark.parametrize(
    "text",
    [
        "home bakery", "Home Bakery", "high-protein breakfast", "cloud kitchen", "tiffin service",
        "catering", "caterer for parties", "homemade pickles and jam", "sweets (mithai) shop",
        "juice bar", "chocolate making", "baking classes", "custom cakes", "chai stall",
        "street food cart", "restaurant", "cookies and biscuits", "paneer and dairy",
    ],
)  # fmt: skip
def test_food_businesses_are_recognised(text: str) -> None:
    assert is_food_business(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "web design", "tutoring", "handmade jewellery", "yoga classes", "teaching maths",
        "steam cleaning", "backend developer", "photography", "candle making", "",
        "consulting", "team building workshops",
    ],
)  # fmt: skip
def test_other_businesses_are_not(text: str) -> None:
    assert is_food_business(text) is False


def test_matching_is_on_whole_words_not_inside_other_words() -> None:
    assert is_food_business("teaching") is False and is_food_business("tea stall") is True
    assert is_food_business("team") is False and is_food_business("meal prep") is True


def test_the_input_is_not_trusted_to_be_short_or_tidy() -> None:
    assert is_food_business("  BAKERY!!  ") is True
    assert is_food_business("x" * 100_000) is False


# ---- in the analyze response ------------------------------------------------------------------


@pytest.mark.parametrize("scenario", IDS)
def test_every_seeded_scenario_is_a_food_business(scenario: str) -> None:
    assert analysis_for(scenario).food_business is True


def analyze_with(category: str, titles: tuple[str, str] = ("Tutoring", "Online courses")) -> bool:
    request = load_demo_catalog().request("noida-feasibility-only")
    assert request is not None
    body = request.model_dump(mode="json")
    body["category"] = category
    body["options"][0]["title"], body["options"][1]["title"] = titles
    result = AnalyzeService(load_dataset(), FakeClock()).analyze(
        AnalyzeRequest.model_validate(body)
    )
    return result.food_business


def test_a_non_food_business_gets_no_food_flag() -> None:
    assert analyze_with("tutoring") is False


def test_a_food_option_title_is_enough_when_the_category_is_vague() -> None:
    assert analyze_with("home business", ("Home bakery", "Online courses")) is True
