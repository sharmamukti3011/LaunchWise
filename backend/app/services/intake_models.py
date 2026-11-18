"""Intake models: what Claude may answer, and the draft the form receives.

Claude's answer is the structured fields only: a value, or null when the description does not
state it. The status of each field ("from your description" or "not mentioned") is set here from
that null, never by Claude, so it cannot be claimed falsely.
"""

import re
from collections.abc import Callable
from decimal import Decimal
from typing import Annotated, Any, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    BeforeValidator,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from app.schemas.text import reject_control_characters

MAX_MONEY = Decimal("10000000")  # the same limits the analyze request enforces
MAX_UNITS_PER_DAY = 10_000
MAX_DAYS_PER_WEEK = 7
MAX_HOURS_PER_WEEK = 168
MAX_MINUTES_PER_UNIT = 1_440
MAX_LIST_ITEMS = 20

DRAFTED_TEXT = "We filled in what you described. Check every field before you run the analysis."
FALLBACK_TEXT = "We could not turn that into a draft. Please fill in the form yourself."
BUDGET_TEXT = (
    "The description helper has reached its limit for now. Please fill in the form yourself."
)


def _plain_number(value: object) -> object:
    """Whole numbers and digit strings only. Floats and booleans are never accepted."""
    if isinstance(value, bool):
        raise ValueError("not a number")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float):
        raise ValueError("floats are not accepted")
    if isinstance(value, str):
        return value.strip().removeprefix("₹").replace(",", "").strip()
    return value


def _money(value: str) -> str:
    if not re.fullmatch(r"\d+(?:\.\d{1,2})?", value) or Decimal(value) > MAX_MONEY:
        raise ValueError("not an amount in rupees")
    return value


def _whole(maximum: int) -> Callable[[str], str]:
    def check(value: str) -> str:
        if not re.fullmatch(r"\d+", value) or int(value) > maximum:
            raise ValueError("not a whole number in range")
        return value

    return check


def _clean(value: str) -> str:
    return reject_control_characters(value)


_CLEAN = AfterValidator(_clean)
Money = Annotated[str, BeforeValidator(_plain_number), AfterValidator(_money)]
UnitsPerDay = Annotated[
    str, BeforeValidator(_plain_number), AfterValidator(_whole(MAX_UNITS_PER_DAY))
]
DaysPerWeek = Annotated[
    str, BeforeValidator(_plain_number), AfterValidator(_whole(MAX_DAYS_PER_WEEK))
]
HoursPerWeek = Annotated[
    str, BeforeValidator(_plain_number), AfterValidator(_whole(MAX_HOURS_PER_WEEK))
]
Minutes = Annotated[
    str, BeforeValidator(_plain_number), AfterValidator(_whole(MAX_MINUTES_PER_UNIT))
]
Title = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80), _CLEAN
]
Place = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=80), _CLEAN
]
Category = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60), _CLEAN
]
Item = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60), _CLEAN]


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    @field_validator("*", mode="before")
    @classmethod
    def _blank_means_not_mentioned(cls, value: Any) -> Any:
        # An empty string or list is the same as null: the description did not say.
        if isinstance(value, str) and not value.strip():
            return None
        if isinstance(value, list) and not value:
            return None
        return value


class ClaudeOption(_Strict):
    title: Title | None = None
    price: Money | None = None
    cost: Money | None = None
    startup: Money | None = None
    minutes: Minutes | None = None


class ClaudeDraft(_Strict):
    """The only shape Claude may answer in. Unknown keys are refused."""

    budget: Money | None = None
    units_per_day: UnitsPerDay | None = None
    days_per_week: DaysPerWeek | None = None
    hours_per_week: HoursPerWeek | None = None
    skills: Annotated[list[Item], Field(max_length=MAX_LIST_ITEMS)] | None = None
    equipment: Annotated[list[Item], Field(max_length=MAX_LIST_ITEMS)] | None = None
    location: Place | None = None
    category: Category | None = None
    original: ClaudeOption
    alternative: ClaudeOption | None = None


# ---- what the form receives -------------------------------------------------------------------

DraftStatus = Literal["from_description", "not_mentioned"]


class DraftField(BaseModel):
    model_config = ConfigDict(frozen=True)

    value: str
    status: DraftStatus


def _field(value: str | list[str] | None) -> DraftField:
    if value is None:
        return DraftField(value="", status="not_mentioned")
    text = ", ".join(value) if isinstance(value, list) else value
    return DraftField(value=text, status="from_description")


class IntakeDraft(BaseModel):
    model_config = ConfigDict(frozen=True)

    budget: DraftField
    units_per_day: DraftField
    days_per_week: DraftField
    hours_per_week: DraftField
    skills: DraftField
    equipment: DraftField
    location: DraftField
    category: DraftField
    original_title: DraftField
    original_price: DraftField
    original_cost: DraftField
    original_startup: DraftField
    original_minutes: DraftField
    alt_title: DraftField
    alt_price: DraftField
    alt_cost: DraftField
    alt_startup: DraftField
    alt_minutes: DraftField
    alternative_mentioned: bool


def to_draft(claude: ClaudeDraft) -> IntakeDraft:
    alt = claude.alternative or ClaudeOption()
    return IntakeDraft(
        budget=_field(claude.budget),
        units_per_day=_field(claude.units_per_day),
        days_per_week=_field(claude.days_per_week),
        hours_per_week=_field(claude.hours_per_week),
        skills=_field(claude.skills),
        equipment=_field(claude.equipment),
        location=_field(claude.location),
        category=_field(claude.category),
        original_title=_field(claude.original.title),
        original_price=_field(claude.original.price),
        original_cost=_field(claude.original.cost),
        original_startup=_field(claude.original.startup),
        original_minutes=_field(claude.original.minutes),
        alt_title=_field(alt.title),
        alt_price=_field(alt.price),
        alt_cost=_field(alt.cost),
        alt_startup=_field(alt.startup),
        alt_minutes=_field(alt.minutes),
        alternative_mentioned=claude.alternative is not None,
    )


class IntakeResponse(BaseModel):
    """`draft` is None for a fallback: the form stays as it was and the message says so."""

    model_config = ConfigDict(frozen=True)

    status: Literal["drafted", "fallback"]
    message: str
    draft: IntakeDraft | None = None
