"""payload_from_model / hash_model: one definition of 'the exact payload' for every caller."""

from datetime import date
from decimal import Decimal
from enum import StrEnum
from typing import Any

import pytest
from pydantic import BaseModel, HttpUrl

from app.engine.approval_payload import SET_LIKE_FIELDS, hash_model, payload_from_model
from app.engine.approval_rules import canonical_hash
from tests.pune_fixtures import profile


class Tier(StrEnum):
    BASIC = "basic"
    PRO = "pro"


class Item(BaseModel):
    sku: str
    price: Decimal


class Plan(BaseModel):
    name: str
    skills: list[str]
    opens_on: date
    tier: Tier
    items: list[Item]
    link: HttpUrl


def plan(**overrides: Any) -> Plan:
    data: dict[str, Any] = {
        "name": "Weekend cakes",
        "skills": ["baking", "decorating"],
        "opens_on": date(2026, 12, 5),
        "tier": Tier.BASIC,
        "items": [Item(sku="choco", price=Decimal("800")), Item(sku="fruit", price=Decimal("650"))],
        "link": "https://example.com/pune",
    }
    data.update(overrides)
    return Plan(**data)


def test_payload_is_plain_data_the_hash_accepts() -> None:
    payload = payload_from_model(plan())
    assert payload["opens_on"] == "2026-12-05"
    assert payload["tier"] == "basic"
    assert isinstance(payload["link"], str)
    assert payload["items"][0] == {"sku": "choco", "price": Decimal("800")}
    canonical_hash(payload)  # must not raise


def test_hash_model_is_canonical_hash_of_the_payload() -> None:
    assert hash_model(plan()) == canonical_hash(payload_from_model(plan()))


def test_same_content_same_hash_and_any_change_differs() -> None:
    assert hash_model(plan()) == hash_model(plan())
    assert hash_model(plan()) != hash_model(plan(name="Weekend cakes!"))
    assert hash_model(plan()) != hash_model(plan(tier=Tier.PRO))
    assert hash_model(plan()) != hash_model(plan(opens_on=date(2026, 12, 6)))


def test_set_like_lists_are_sorted_before_hashing() -> None:
    forward = plan(skills=["baking", "decorating", "piping"])
    shuffled = plan(skills=["piping", "baking", "decorating"])
    assert hash_model(forward) == hash_model(shuffled)
    assert payload_from_model(shuffled)["skills"] == sorted(["baking", "decorating", "piping"])


def test_set_like_lists_ignore_duplicates() -> None:
    assert hash_model(plan(skills=["baking", "baking"])) == hash_model(plan(skills=["baking"]))


def test_set_like_sorting_applies_to_nested_models() -> None:
    a = profile(skills=["baking", "decorating"], equipment=["oven", "mixer"])
    b = profile(skills=["decorating", "baking"], equipment=["mixer", "oven"])
    assert hash_model(a) == hash_model(b)
    assert payload_from_model(b)["equipment"] == ["mixer", "oven"]


def test_set_like_field_names_are_the_documented_ones() -> None:
    assert {"skills", "equipment", "required_skills", "required_equipment"} <= SET_LIKE_FIELDS


def test_other_lists_keep_their_order() -> None:
    swapped = plan(items=list(reversed(plan().items)))
    assert hash_model(plan()) != hash_model(swapped)


def test_different_set_members_still_differ() -> None:
    assert hash_model(plan(skills=["baking"])) != hash_model(plan(skills=["baking", "piping"]))


def test_model_dict_model_round_trip_keeps_the_hash() -> None:
    original = plan(skills=["decorating", "baking"])
    payload = payload_from_model(original)
    rebuilt = Plan.model_validate(payload)
    assert hash_model(rebuilt) == hash_model(original)
    assert payload_from_model(rebuilt) == payload


def test_round_trip_holds_for_a_real_profile() -> None:
    original = profile(skills=["decorating", "baking"])
    rebuilt = type(original).model_validate(payload_from_model(original))
    assert hash_model(rebuilt) == hash_model(original)


def test_equal_decimals_in_models_hash_the_same() -> None:
    a = plan(items=[Item(sku="x", price=Decimal("1.50"))])
    b = plan(items=[Item(sku="x", price=Decimal("1.5"))])
    assert hash_model(a) == hash_model(b)


def test_float_fields_are_rejected_not_silently_hashed() -> None:
    class Loose(BaseModel):
        price: float

    with pytest.raises(TypeError, match="float"):
        hash_model(Loose(price=1.5))
