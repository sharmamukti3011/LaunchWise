"""StorefrontConfig: frozen, length-limited, no float money, and hashable for approvals."""

import json
from decimal import Decimal
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

from app.engine.approval_payload import hash_model, payload_from_model
from app.engine.approval_rules import canonical_hash
from app.schemas.storefront import MAX_PRICE, StorefrontConfig

D = Decimal


def config_data(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "brand": "Aarti's Home Bakery",
        "tagline": "Fresh cakes baked at home in Pune, every weekend.",
        "products": [
            {"name": "Chocolate cake (1 kg)", "description": "Rich and moist.", "price": "800.00"},
            {"name": "Fruit cake (500 g)", "price": "450"},
        ],
        "availability": {"days": ["sat", "sun"], "note": "Order by Thursday evening."},
        "capacity_note": "About 3 cakes a day, so slots fill up fast.",
        "contact_form_enabled": True,
    }
    data.update(overrides)
    return data


def build(**overrides: Any) -> StorefrontConfig:
    return StorefrontConfig.model_validate(config_data(**overrides))


def with_product(**fields: Any) -> dict[str, Any]:
    return {"products": [{"name": "Cake", "price": "100", **fields}]}


# ---- shape ------------------------------------------------------------------------------------


def test_a_valid_config_builds_with_sensible_defaults() -> None:
    config = build()
    assert config.brand == "Aarti's Home Bakery"
    assert config.products[0].price == D("800.00")
    assert config.products[1].description == ""
    assert config.contact_form_enabled is True


def test_the_contact_form_is_off_unless_asked_for() -> None:
    data = config_data()
    del data["contact_form_enabled"]
    assert StorefrontConfig.model_validate(data).contact_form_enabled is False


def test_the_model_is_frozen() -> None:
    config = build()
    with pytest.raises(ValidationError):
        config.brand = "Changed"  # type: ignore[misc]
    with pytest.raises(ValidationError):
        config.products[0].price = D("1")  # type: ignore[misc]
    assert config.availability is not None
    with pytest.raises(ValidationError):
        config.availability.note = "x"  # type: ignore[misc]


@pytest.mark.parametrize(
    "extra", [{"html": "<b>x</b>"}, {"template": "evil"}, {"script": "alert(1)"}]
)
def test_unknown_fields_are_rejected_so_no_markup_or_code_can_ride_along(
    extra: dict[str, Any],
) -> None:
    with pytest.raises(ValidationError):
        build(**extra)
    with pytest.raises(ValidationError):
        build(**with_product(**extra))
    with pytest.raises(ValidationError):
        build(availability={"days": ["sat"], **extra})


def test_surrounding_whitespace_is_trimmed() -> None:
    config = build(brand="  Aarti's  ", tagline="  Fresh.  ")
    assert (config.brand, config.tagline) == ("Aarti's", "Fresh.")


# ---- text limits ------------------------------------------------------------------------------

LIMITS: list[tuple[str, int, Any, bool]] = [
    # (label, maximum length, builder taking the text, required)
    ("brand", 60, lambda t: {"brand": t}, True),
    ("tagline", 120, lambda t: {"tagline": t}, True),
    ("capacity_note", 200, lambda t: {"capacity_note": t}, True),
    ("product name", 60, lambda t: with_product(name=t), True),
    ("product description", 200, lambda t: with_product(description=t), False),
    ("availability note", 120, lambda t: {"availability": {"days": ["sat"], "note": t}}, False),
]


@pytest.mark.parametrize(("label", "maximum", "make", "required"), LIMITS)
def test_every_text_field_has_a_length_limit_checked_at_the_edge(
    label: str, maximum: int, make: Any, required: bool
) -> None:
    build(**make("x" * maximum))
    with pytest.raises(ValidationError):
        build(**make("x" * (maximum + 1)))


@pytest.mark.parametrize(("label", "maximum", "make", "required"), LIMITS)
def test_required_text_may_not_be_empty_or_blank(
    label: str, maximum: int, make: Any, required: bool
) -> None:
    if required:
        for blank in ("", "   "):
            with pytest.raises(ValidationError):
                build(**make(blank))
    else:
        build(**make(""))  # optional text may be empty


@pytest.mark.parametrize(("label", "maximum", "make", "required"), LIMITS)
@pytest.mark.parametrize("bad", ["a\nb", "a\r\nb", "a\x00b", "a\tb", "a b", "a\x1bb"])
def test_every_text_field_rejects_control_characters(
    label: str, maximum: int, make: Any, required: bool, bad: str
) -> None:
    with pytest.raises(ValidationError):
        build(**make(bad))


def test_markup_like_text_is_kept_as_is_because_the_template_escapes_at_render() -> None:
    config = build(brand="<b>Cakes</b> & Co", tagline='5 > 3 && "quotes"')
    assert config.brand == "<b>Cakes</b> & Co"


def test_text_in_indian_scripts_is_accepted() -> None:
    assert build(brand="आरतीची होम बेकरी").brand == "आरतीची होम बेकरी"


# ---- products and prices ----------------------------------------------------------------------


def test_between_one_and_twelve_products() -> None:
    one = [{"name": "Cake", "price": "100"}]
    twelve = [{"name": f"Cake {i}", "price": "100"} for i in range(12)]
    assert len(build(products=one).products) == 1
    assert len(build(products=twelve).products) == 12
    with pytest.raises(ValidationError):
        build(products=[])
    with pytest.raises(ValidationError):
        build(products=[*twelve, {"name": "Cake 13", "price": "100"}])


def test_product_names_must_be_unique_ignoring_case() -> None:
    with pytest.raises(ValidationError):
        build(products=[{"name": "Cake", "price": "1"}, {"name": " cake ", "price": "2"}])


@pytest.mark.parametrize("price", ["800", "800.00", "0.01", 800, "100000", "100000.00"])
def test_valid_prices(price: Any) -> None:
    assert build(**with_product(price=price)).products[0].price == D(str(price))


@pytest.mark.parametrize(
    "price", ["0", "0.00", "-1", "100000.01", "800.001", "NaN", "Infinity", "-Infinity", "abc", ""]
)
def test_invalid_prices_are_rejected(price: Any) -> None:
    with pytest.raises(ValidationError):
        build(**with_product(price=price))


def test_floats_are_rejected_as_money_in_python_and_in_json() -> None:
    with pytest.raises(ValidationError):
        build(**with_product(price=800.5))
    as_json = (
        StorefrontConfig.model_validate(config_data())
        .model_dump_json()
        .replace('"800.00"', "800.5")
    )
    assert "800.5" in as_json
    with pytest.raises(ValidationError):
        StorefrontConfig.model_validate_json(as_json)


def test_the_price_ceiling_is_documented_in_one_constant() -> None:
    assert D("100000") == MAX_PRICE


# ---- availability -----------------------------------------------------------------------------


def test_days_are_put_into_week_order_so_equal_sets_are_equal() -> None:
    config = build(availability={"days": ["sun", "fri", "sat"]})
    assert config.availability is not None
    assert config.availability.days == ["fri", "sat", "sun"]


@pytest.mark.parametrize(
    "days", [[], ["sat", "sat"], ["saturday"], ["funday"], ["mon"] * 8, [1, 2]]
)
def test_invalid_days_are_rejected(days: list[Any]) -> None:
    with pytest.raises(ValidationError):
        build(availability={"days": days})


def test_all_seven_days_are_allowed() -> None:
    days = ["sun", "sat", "fri", "thu", "wed", "tue", "mon"]
    config = build(availability={"days": days})
    assert config.availability is not None
    assert config.availability.days == ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


# ---- hashing for approvals --------------------------------------------------------------------


def test_the_payload_is_plain_data_the_hash_accepts_and_keeps_prices_as_decimals() -> None:
    payload = payload_from_model(build())
    canonical_hash(payload)  # must not raise
    assert payload["products"][0]["price"] == D("800.00")
    assert payload["availability"]["days"] == ["sat", "sun"]
    assert payload["contact_form_enabled"] is True


def test_equal_content_hashes_equal_whatever_the_input_spelling() -> None:
    a = build(products=[{"name": "Cake", "price": "800.00"}], availability={"days": ["sun", "sat"]})
    b = build(products=[{"name": "Cake", "price": "800"}], availability={"days": ["sat", "sun"]})
    assert hash_model(a) == hash_model(b)


def test_json_round_trip_keeps_the_hash() -> None:
    original = build()
    rebuilt = StorefrontConfig.model_validate_json(original.model_dump_json())
    assert hash_model(rebuilt) == hash_model(original)
    assert StorefrontConfig.model_validate(payload_from_model(original)) == original


CHOCOLATE = {"name": "Chocolate cake (1 kg)", "description": "Rich and moist.", "price": "800.00"}
FRUIT = {"name": "Fruit cake (500 g)", "price": "450"}


@pytest.mark.parametrize(
    "change",
    [
        {"brand": "Other Bakery"},
        {"tagline": "Different."},
        {"capacity_note": "About 4 cakes a day."},
        {"contact_form_enabled": False},
        {"availability": {"days": ["sat"], "note": "Order by Thursday evening."}},
        {"availability": {"days": ["sat", "sun"], "note": "Order by Friday."}},
        {"products": [{**CHOCOLATE, "price": "801"}, FRUIT]},
        {"products": [FRUIT, CHOCOLATE]},  # product order is meaningful
    ],
)
def test_any_change_to_any_field_changes_the_hash(change: dict[str, Any]) -> None:
    assert hash_model(build(**change)) != hash_model(build())


# ---- generic: no bakery assumptions -----------------------------------------------------------

NOIDA_BREAKFAST: dict[str, Any] = {
    "brand": "ProteinStart Noida",
    "tagline": "High-protein breakfasts, delivered fresh before 9 am.",
    "products": [
        {"name": "Paneer bhurji bowl", "description": "About 28 g protein.", "price": "180"},
        {"name": "Sprouts and egg plate", "price": "150.00"},
    ],
    "availability": {
        "days": ["mon", "tue", "wed", "thu", "fri", "sat"],
        "note": "Order the night before.",
    },
    "capacity_note": "We prepare about 40 breakfasts a day.",
    "contact_form_enabled": True,
}


def test_a_non_bakery_business_in_noida_validates_and_hashes() -> None:
    config = StorefrontConfig.model_validate(NOIDA_BREAKFAST)
    assert config.availability is not None
    assert config.availability.days == ["mon", "tue", "wed", "thu", "fri", "sat"]
    digest = hash_model(config)
    assert len(digest) == 64
    assert hash_model(StorefrontConfig.model_validate_json(config.model_dump_json())) == digest
    assert digest != hash_model(build())  # different business, different hash


def test_the_schema_assumes_no_particular_business() -> None:
    words = ("cake", "bak", "bread", "pastry", "oven", "pune")
    schema_text = json.dumps(StorefrontConfig.model_json_schema()).lower()
    source = Path(__file__).resolve().parents[1] / "app" / "schemas" / "storefront.py"
    for word in words:
        assert word not in schema_text, f"schema mentions {word!r}"
        assert word not in source.read_text().lower(), f"storefront.py mentions {word!r}"


# ---- the starter-page additions: optional, so nothing is invented for the owner ---------------


def minimal() -> dict[str, Any]:
    return {"brand": "Aarti's", "products": [{"name": "Cake", "price": "500"}]}


def test_a_starter_page_needs_only_a_brand_and_one_product() -> None:
    config = StorefrontConfig.model_validate(minimal())
    assert config.tagline is None and config.availability is None and config.capacity_note is None
    assert config.description == "" and config.contact_email is None
    assert config.food_notice is False and config.contact_form_enabled is False


def test_the_description_is_limited_to_300_characters_without_control_characters() -> None:
    StorefrontConfig.model_validate({**minimal(), "description": "d" * 300})
    for bad in ("d" * 301, "a\nb"):
        with pytest.raises(ValidationError):
            StorefrontConfig.model_validate({**minimal(), "description": bad})


@pytest.mark.parametrize("email", ["a@example.com", "a.b+c@sub.example.in"])
def test_the_contact_email_is_plain_text_that_looks_like_an_address(email: str) -> None:
    assert (
        StorefrontConfig.model_validate({**minimal(), "contact_email": email}).contact_email
        == email
    )


@pytest.mark.parametrize(
    "email", ["nope", "a@b", "a@b.com\nBcc: x@y.z", "<a@b.com>", "mailto:a@b.com"]
)
def test_a_bad_contact_email_is_rejected(email: str) -> None:
    with pytest.raises(ValidationError):
        StorefrontConfig.model_validate({**minimal(), "contact_email": email})


@pytest.mark.parametrize(
    "change",
    [{"description": "A shop."}, {"contact_email": "a@example.com"}, {"food_notice": True}],
)
def test_the_new_fields_are_part_of_the_approved_hash(change: dict[str, Any]) -> None:
    base = StorefrontConfig.model_validate(minimal())
    assert hash_model(StorefrontConfig.model_validate({**minimal(), **change})) != hash_model(base)
