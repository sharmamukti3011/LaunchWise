"""The page template: escapes everything, carries noindex and the example banner, no scripts."""

from decimal import Decimal
from html.parser import HTMLParser
from typing import Any

import pytest

from app.schemas.storefront import StorefrontConfig
from app.services.storefront_render import ICON_LINKS, STYLESHEET_PATH, render_page

D = Decimal
ALLOWED_TAGS = {
    "html", "head", "meta", "title", "link", "body", "div", "main", "h1", "h2", "p", "section",
    "footer", "a", "ul", "li", "span", "strong",
}  # fmt: skip


def config(**overrides: Any) -> StorefrontConfig:
    data: dict[str, Any] = {
        "brand": "Aarti's Home Bakery",
        "description": "Fresh cakes, baked to order.",
        "products": [{"name": "Custom celebration cakes", "price": "1200"}],
        "contact_email": "aarti@example.com",
        "food_notice": True,
    }
    data.update(overrides)
    return StorefrontConfig.model_validate(data)


class Collector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.tags: list[str] = []
        self.attrs: list[tuple[str, str, str | None]] = []
        self.text: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        self.tags.append(tag)
        self.attrs.extend((tag, name, value) for name, value in attrs)

    def handle_data(self, data: str) -> None:
        self.text.append(data)


def parse(html: str) -> Collector:
    collector = Collector()
    collector.feed(html)
    return collector


# ---- the guardrails every page carries --------------------------------------------------------


def test_every_page_says_noindex_in_the_document() -> None:
    page = parse(render_page(config()))
    assert ("meta", "name", "robots") in page.attrs
    assert ("meta", "content", "noindex, nofollow") in page.attrs


def test_every_page_carries_the_example_banner_and_the_made_with_footer() -> None:
    html = render_page(config())
    page = parse(html)
    text = " ".join(page.text)
    assert "Example page made with LaunchWise" in text
    assert "Made with LaunchWise" in text
    assert html.index("Example page made with LaunchWise") < html.index("<h1")  # banner first


def test_the_page_is_a_complete_responsive_document_that_follows_the_visitors_colour_scheme() -> (
    None
):
    html = render_page(config())
    assert html.startswith("<!doctype html>") and '<html lang="en">' in html
    assert 'name="viewport" content="width=device-width, initial-scale=1.0"' in html
    assert 'name="color-scheme" content="light dark"' in html


def test_nothing_but_simple_text_tags_is_used() -> None:
    page = parse(render_page(config()))
    assert set(page.tags) <= ALLOWED_TAGS, set(page.tags) - ALLOWED_TAGS


@pytest.mark.parametrize(
    "forbidden",
    [
        "script",
        "img",
        "iframe",
        "form",
        "style",
        "svg",
        "object",
        "embed",
        "video",
        "audio",
        "input",
        "button",
    ],
)
def test_no_script_image_frame_form_or_style_element_ever_appears(forbidden: str) -> None:
    assert forbidden not in parse(render_page(config())).tags


def test_no_inline_styles_or_event_handlers_because_the_site_forbids_them() -> None:
    names = {name for _, name, _ in parse(render_page(config())).attrs}
    assert "style" not in names
    assert not any(name.startswith("on") for name in names)


def test_the_only_links_are_our_stylesheet_our_icons_and_the_footer_link_home() -> None:
    page = parse(render_page(config()))
    links = [(tag, name, value) for tag, name, value in page.attrs if name in ("href", "src")]
    icons = [("link", "href", href) for _, href in ICON_LINKS]
    expected = [("link", "href", STYLESHEET_PATH), ("a", "href", "/"), *icons]
    assert sorted(links) == sorted(expected)
    assert all(
        href is not None and href.startswith("/") for _, _, href in links
    )  # all local, none off-site
    assert page.tags.count("a") == 1


def test_the_email_is_shown_as_plain_text_never_as_a_link() -> None:
    html = render_page(config())
    assert "aarti@example.com" in " ".join(parse(html).text)
    assert "mailto" not in html and parse(html).tags.count("a") == 1


# ---- escaping ---------------------------------------------------------------------------------

ATTACK = "<script>alert('x')</script> & \"quotes\" <b>bold</b>"


def test_all_user_text_is_escaped() -> None:
    cfg = config(
        brand=ATTACK[:60],
        description=ATTACK[:300],
        products=[{"name": ATTACK[:60], "description": ATTACK[:200], "price": "10"}],
    )
    html = render_page(cfg)
    page = parse(html)
    assert "script" not in page.tags and "b" not in page.tags
    assert "<script" not in html and "<b>" not in html
    assert "&lt;script&gt;" in html and "&amp;" in html


def test_quotes_cannot_break_out_of_an_attribute() -> None:
    html = render_page(config(brand='" onmouseover="alert(1)'))
    assert 'onmouseover="' not in html and "&quot; onmouseover=&quot;" in html
    names = {name for _, name, _ in parse(html).attrs}
    assert "onmouseover" not in names


def test_text_in_indian_scripts_renders() -> None:
    html = render_page(config(brand="आरती की बेकरी"))
    assert "आरती की बेकरी" in html


# ---- content ----------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("price", "shown"), [("1200", "₹1,200"), ("899.50", "₹899.50"), ("5", "₹5")]
)
def test_the_price_is_shown_in_rupees_without_needless_paise(price: str, shown: str) -> None:
    cfg = config(products=[{"name": "Cake", "price": price}])
    assert shown in " ".join(parse(render_page(cfg)).text)


def test_the_page_shows_name_offer_and_description() -> None:
    text = " ".join(parse(render_page(config())).text)
    for expected in (
        "Aarti's Home Bakery",
        "Custom celebration cakes",
        "Fresh cakes, baked to order.",
    ):
        assert expected in text


def test_the_fssai_note_appears_only_for_food_businesses() -> None:
    note = "Selling food from home requires FSSAI registration before you start."
    assert note in " ".join(parse(render_page(config(food_notice=True))).text)
    assert note not in " ".join(parse(render_page(config(food_notice=False))).text)


def test_optional_parts_are_left_out_when_not_given() -> None:
    text = " ".join(parse(render_page(config(contact_email=None, description=""))).text)
    assert "Contact" not in text and "aarti@example.com" not in text
    assert "Fresh cakes" not in text


def test_a_general_config_with_tagline_days_and_capacity_still_renders_them() -> None:
    cfg = config(
        tagline="Baked fresh.",
        availability={"days": ["sat", "sun"], "note": "Order by Thursday."},
        capacity_note="About 3 cakes a day.",
    )
    text = " ".join(parse(render_page(cfg)).text)
    for expected in ("Baked fresh.", "Sat", "Sun", "Order by Thursday.", "About 3 cakes a day."):
        assert expected in text


def test_the_template_assumes_no_particular_business() -> None:
    from pathlib import Path

    source = (Path(__file__).parents[1] / "app" / "services" / "storefront_render.py").read_text()
    for word in ("cake", "bak", "bread", "pastry", "oven", "pune"):
        assert word not in source.lower(), word


def test_rendering_is_deterministic() -> None:
    assert render_page(config()) == render_page(config())


def test_several_products_all_render() -> None:
    cfg = config(products=[{"name": "A", "price": "1"}, {"name": "B", "price": "2"}])
    page = parse(render_page(cfg))
    assert page.tags.count("section") == 2
