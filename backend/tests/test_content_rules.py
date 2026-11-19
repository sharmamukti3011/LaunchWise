"""Public-page text rules: no markup, no links, no obvious abuse. Refused with a fixed code."""

import pytest

from app.services.content_rules import contains_markup_or_link, is_blocked


@pytest.mark.parametrize(
    "text",
    [
        "Aarti's Home Bakery",
        "Fresh cakes, baked at home in Pune.",
        "Rs 500 per cake (1 kg)",
        "Open Sat & Sun",
        "Café déjà vu",
        "आरती की बेकरी",
        "Order by 9 am!",
    ],
)
def test_ordinary_text_is_clean(text: str) -> None:
    assert contains_markup_or_link(text) is False


@pytest.mark.parametrize(
    "text",
    [
        "<b>bold</b>",
        "a < b",
        "a > b",
        "<script>alert(1)</script>",
        "<img src=x>",
        "see http://example.com",
        "see https://example.com/page",
        "HTTPS://EXAMPLE.COM",
        "ftp://files.example",
        "javascript:alert(1)",
        "data:text/html,hi",
        "www.example.com",
        "visit example.com today",
        "shop at my-site.in",
        "order at cakes.co.in",
        "bit.ly/abc",
        "[click](http://x)",
        "[click](x)",
        "me@example.com",
        "@handle",
        "email me at a@b.co",
        "&lt;b&gt;",
        "&#60;b&#62;",
        "https ://example.com",
        "w w w.example . com",
        "example . com",
    ],
)
def test_markup_links_emails_and_addresses_are_refused(text: str) -> None:
    assert contains_markup_or_link(text) is True


def test_a_full_stop_between_words_is_not_a_web_address() -> None:
    assert contains_markup_or_link("We bake. Cakes sell out.") is False
    assert contains_markup_or_link("Open 9.30 am to 5.30 pm") is False
    assert contains_markup_or_link("Price Rs.500") is False


@pytest.mark.parametrize(
    "text",
    [
        "porn", "PORN", "Free Porn Shop", "xxx videos", "escort service", "online casino",
        "betting tips", "buy cocaine", "heroin", "ponzi scheme", "phishing kit",
        "easy money scam", "counterfeit notes", "buy guns", "weapon store", "kill them",
        "nazi gear", "p0rn", "c a s i n o", "pOrN", "porrrn", "casino!!!",
    ],
)  # fmt: skip
def test_obvious_abuse_terms_are_blocked_including_simple_disguises(text: str) -> None:
    assert is_blocked(text) is True


@pytest.mark.parametrize(
    "text",
    [
        "Aarti's Home Bakery", "Essex Cakes", "Sussex Bakes", "Scunthorpe Cakes", "Classic Cakes",
        "Assess Your Taste", "Cocktail Napkins", "Passport Photos Cafe", "Therapist Bakes",
        "Skilled Baker", "Peacock Sweets", "Gunjan Sweets", "Weaponsmith",  # whole words only
        "Cakes for Everyone", "Pune Chai House", "आरती की बेकरी", "",
    ],
)  # fmt: skip
def test_ordinary_names_are_not_blocked_by_a_substring_match(text: str) -> None:
    assert is_blocked(text) is False


def test_the_check_ignores_case_accents_zero_width_characters_and_repeats() -> None:
    assert is_blocked("P​ORN") is True  # a zero-width space inside the word
    assert is_blocked("Pörn") is True
    assert is_blocked("Ｐｏｒｎ") is True  # full-width letters


def test_the_blocklist_is_a_small_reviewable_list_of_whole_words() -> None:
    from app.services.content_rules import BLOCKED_TERMS

    assert 20 <= len(BLOCKED_TERMS) <= 200
    assert all(term == term.lower() and " " not in term for term in BLOCKED_TERMS)
