"""StarterPageRequest: what an owner may type for a public page, and how it becomes a config."""

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.engine.approval_payload import hash_model
from app.schemas.starter import StarterPageRequest, to_config
from app.schemas.storefront import StorefrontConfig

D = Decimal


def build(**overrides: Any) -> StarterPageRequest:
    data: dict[str, Any] = {
        "business_name": "Aarti's Home Bakery",
        "description": "Fresh cakes, baked to order.",
        "contact_email": "aarti@example.com",
        "offer_title": "Custom celebration cakes",
        "offer_price": "1200",
        "food_business": True,
    }
    data.update(overrides)
    return StarterPageRequest.model_validate(data)


def test_a_complete_request_builds() -> None:
    request = build()
    assert request.offer_price == D("1200") and request.food_business is True


def test_description_and_email_are_optional() -> None:
    request = build(description=None, contact_email=None)
    assert request.description == "" and request.contact_email is None
    assert build(description="", contact_email="").contact_email is None  # blank means none


def test_the_limits_are_name_60_description_300_offer_60() -> None:
    build(business_name="n" * 60, description="d" * 300, offer_title="o" * 60)
    for field, size in (("business_name", 61), ("description", 301), ("offer_title", 61)):
        with pytest.raises(ValidationError):
            build(**{field: "x" * size})


@pytest.mark.parametrize("field", ["business_name", "offer_title"])
def test_name_and_offer_are_required_and_not_blank(field: str) -> None:
    for blank in ("", "   "):
        with pytest.raises(ValidationError):
            build(**{field: blank})


@pytest.mark.parametrize("field", ["business_name", "description", "offer_title"])
@pytest.mark.parametrize("bad", ["a\nb", "a\x00b", "a\tb", "a b"])
def test_control_characters_are_refused(field: str, bad: str) -> None:
    with pytest.raises(ValidationError):
        build(**{field: bad})


@pytest.mark.parametrize("field", ["business_name", "description", "offer_title"])
@pytest.mark.parametrize(
    "bad", ["<b>x</b>", "see https://example.com", "visit example.com", "a@b.co", "[x](y)"]
)
def test_markup_links_and_emails_are_refused_in_every_free_text_field(field: str, bad: str) -> None:
    with pytest.raises(ValidationError) as caught:
        build(**{field: bad})
    assert "no_links_or_markup" in str(caught.value)


@pytest.mark.parametrize("field", ["business_name", "description", "offer_title"])
def test_obvious_abuse_terms_are_refused_with_a_fixed_code(field: str) -> None:
    with pytest.raises(ValidationError) as caught:
        build(**{field: "Free porn here"})
    assert "not_allowed" in str(caught.value)
    assert "porn" not in str(caught.value).lower().replace("free porn here", "")  # no echo of why


@pytest.mark.parametrize("email", ["aarti@example.com", "a.b+c@sub.example.co.in", "x@y.in"])
def test_ordinary_emails_are_accepted(email: str) -> None:
    assert build(contact_email=email).contact_email == email


@pytest.mark.parametrize(
    "email",
    ["nope", "a@b", "@example.com", "a@@b.com", "a b@example.com", "a@b.com\nBcc: x@y.z",
     "<a@b.com>", "x" * 250 + "@example.com"],
)  # fmt: skip
def test_bad_emails_are_refused(email: str) -> None:
    with pytest.raises(ValidationError):
        build(contact_email=email)


@pytest.mark.parametrize("price", ["0", "-1", "100001", "1.234", "abc", 12.5, None])
def test_bad_prices_are_refused_and_floats_never_accepted(price: Any) -> None:
    with pytest.raises(ValidationError):
        build(offer_price=price)


@pytest.mark.parametrize("price", ["1", "1200", "899.50", "100000", 500])
def test_good_prices_are_accepted(price: Any) -> None:
    assert build(offer_price=price).offer_price > 0


def test_unknown_fields_are_refused_so_a_client_cannot_add_markup_or_a_slug() -> None:
    for extra in ({"html": "<b>"}, {"slug": "my-page"}, {"expires": "never"}):
        with pytest.raises(ValidationError):
            build(**extra)


def test_the_request_becomes_a_storefront_config_with_nothing_invented() -> None:
    config = to_config(build())
    assert isinstance(config, StorefrontConfig)
    assert config.brand == "Aarti's Home Bakery"
    assert config.description == "Fresh cakes, baked to order."
    assert config.contact_email == "aarti@example.com"
    assert [(p.name, p.price) for p in config.products] == [("Custom celebration cakes", D("1200"))]
    assert config.food_notice is True
    # Never made up for the owner: opening days, capacity, a tagline, a contact form.
    assert config.availability is None and config.capacity_note is None and config.tagline is None
    assert config.contact_form_enabled is False


def test_the_same_request_always_gives_the_same_hash() -> None:
    assert hash_model(to_config(build())) == hash_model(to_config(build()))
    assert hash_model(to_config(build())) != hash_model(to_config(build(offer_price="1201")))
