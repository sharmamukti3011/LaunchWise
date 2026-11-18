"""AnalyzeRequest: input limits, strictness, and compatibility with the domain models."""

from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.services.analyze_models import (
    MAX_MONEY,
    MAX_OPTIONS,
    AnalyzeRequest,
)
from app.services.strategy_models import ConstraintProfile, StrategyOption

D = Decimal


def profile(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "budget": "10000",
        "units_per_day": 3,
        "days_per_week": 2,
        "hours_per_week": {"value": 12, "source": "assumption"},
        "skills": ["baking"],
        "equipment": ["oven"],
        "location": "Pune",
    }
    data.update(overrides)
    return data


def option(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "id": "original-cakes",
        "title": "Everyday cakes",
        "is_original": True,
        "price": "500",
        "variable_cost_per_unit": "200",
        "fixed_startup_costs": "3000",
        "minutes_per_unit": {"value": 60, "source": "user_provided"},
    }
    data.update(overrides)
    return data


def alternative(n: int = 1, **overrides: Any) -> dict[str, Any]:
    return option(id=f"alt-{n}", title=f"Alternative {n}", is_original=False, **overrides)


def request(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "profile": profile(),
        "category": "home bakery",
        "options": [option()],
    }
    data.update(overrides)
    return data


def build(**overrides: Any) -> AnalyzeRequest:
    return AnalyzeRequest.model_validate(request(**overrides))


def test_a_minimal_valid_request_builds_with_domain_compatible_models() -> None:
    req = build()
    assert isinstance(req.profile, ConstraintProfile)
    assert isinstance(req.options[0], StrategyOption)
    assert req.profile.budget == D("10000")


def test_json_round_trip() -> None:
    req = build(options=[option(), alternative(opportunity_id="TODO-VERIFY-PUNE-001")])
    assert AnalyzeRequest.model_validate_json(req.model_dump_json()) == req


# ---- option count and shape -------------------------------------------------------------------


def test_between_one_and_six_options() -> None:
    six = [option(), *[alternative(i) for i in range(1, MAX_OPTIONS)]]
    assert len(build(options=six).options) == MAX_OPTIONS
    with pytest.raises(ValidationError):
        build(options=[])
    with pytest.raises(ValidationError):
        build(options=[*six, alternative(99)])


def test_exactly_one_option_is_the_original() -> None:
    with pytest.raises(ValidationError):
        build(options=[alternative(1)])
    with pytest.raises(ValidationError):
        build(options=[option(), option(id="another")])


def test_option_ids_are_unique() -> None:
    with pytest.raises(ValidationError):
        build(options=[option(), alternative(1), alternative(1)])


@pytest.mark.parametrize("where", ["request", "profile", "option", "sourced"])
def test_unknown_fields_are_rejected_everywhere(where: str) -> None:
    extra = {"unexpected": "x"}
    data = request()
    if where == "request":
        data.update(extra)
    elif where == "profile":
        data["profile"].update(extra)
    elif where == "option":
        data["options"][0].update(extra)
    else:
        data["profile"]["hours_per_week"].update(extra)
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate(data)


# ---- identifiers and text ---------------------------------------------------------------------


@pytest.mark.parametrize("good", ["a", "original-cakes", "alt_2", "0abc", "x" * 40])
def test_valid_ids(good: str) -> None:
    assert build(options=[option(id=good)]).options[0].id == good


@pytest.mark.parametrize(
    "bad", ["", "Original", "has space", "-lead", "_lead", "x" * 41, "é", "a/b"]
)
def test_invalid_option_ids(bad: str) -> None:
    with pytest.raises(ValidationError):
        build(options=[option(id=bad)])


@pytest.mark.parametrize("good", ["TODO-VERIFY-PUNE-001", "TEST-FAKE-001", "abc_1", "X" * 40])
def test_opportunity_ids_follow_the_datasets_upper_case_style(good: str) -> None:
    built = build(options=[option(), alternative(opportunity_id=good)])
    assert built.options[1].opportunity_id == good


@pytest.mark.parametrize("bad", ["", " ", "has space", "-lead", "x" * 41, "é", "a/b", "A\nB"])
def test_invalid_opportunity_ids(bad: str) -> None:
    with pytest.raises(ValidationError):
        build(options=[option(), alternative(opportunity_id=bad)])


@pytest.mark.parametrize(
    "make",
    [
        lambda t: request(category=t),
        lambda t: request(profile=profile(location=t)),
        lambda t: request(options=[option(title=t)]),
    ],
)
def test_text_fields_are_bounded_trimmed_and_free_of_control_characters(make: Any) -> None:
    for blank in ("", "   "):
        with pytest.raises(ValidationError):
            AnalyzeRequest.model_validate(make(blank))
    for bad in ("a\nb", "a\x00b", "a\tb", "a b"):
        with pytest.raises(ValidationError):
            AnalyzeRequest.model_validate(make(bad))
    with pytest.raises(ValidationError):
        AnalyzeRequest.model_validate(make("x" * 201))


def test_lists_of_skills_and_equipment_are_bounded() -> None:
    twenty = [f"skill {i}" for i in range(20)]
    assert len(build(profile=profile(skills=twenty)).profile.skills) == 20
    with pytest.raises(ValidationError):
        build(profile=profile(skills=[*twenty, "one more"]))
    with pytest.raises(ValidationError):
        build(profile=profile(equipment=[*twenty, "one more"]))
    with pytest.raises(ValidationError):
        build(options=[option(required_skills=[*twenty, "one more"])])
    with pytest.raises(ValidationError):
        build(options=[option(required_equipment=["x" * 61])])
    with pytest.raises(ValidationError):
        build(profile=profile(skills=["bad\nskill"]))


# ---- numbers ----------------------------------------------------------------------------------


@pytest.mark.parametrize("field", ["price", "variable_cost_per_unit", "fixed_startup_costs"])
def test_option_money_is_bounded_two_decimals_and_never_a_float(field: str) -> None:
    assert build(options=[option(**{field: str(MAX_MONEY)})])
    for bad in (str(MAX_MONEY + 1), "10.001", "-1", 12.5, "NaN", "Infinity"):
        with pytest.raises(ValidationError):
            build(options=[option(**{field: bad})])


def test_budget_is_bounded_two_decimals_and_never_a_float() -> None:
    assert build(profile=profile(budget=str(MAX_MONEY)))
    for bad in (str(MAX_MONEY + 1), "10.001", "-1", 99.5, "NaN"):
        with pytest.raises(ValidationError):
            build(profile=profile(budget=bad))


def test_capacity_numbers_are_bounded() -> None:
    assert build(profile=profile(units_per_day=10_000))
    for bad in (10_001, -1):
        with pytest.raises(ValidationError):
            build(profile=profile(units_per_day=bad))
    for bad in (8, -1):
        with pytest.raises(ValidationError):
            build(profile=profile(days_per_week=bad))
    with pytest.raises(ValidationError):
        build(profile=profile(hours_per_week={"value": 169, "source": "user_provided"}))
    assert build(options=[option(minutes_per_unit={"value": 1440, "source": "assumption"})])
    with pytest.raises(ValidationError):
        build(options=[option(minutes_per_unit={"value": 1441, "source": "assumption"})])
