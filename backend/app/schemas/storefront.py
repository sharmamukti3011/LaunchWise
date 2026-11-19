"""StorefrontConfig: the validated JSON content a template renders into a storefront.

Claude (or anyone) supplies content only, never HTML or code. Every text field has a length limit
and rejects control characters; the template escapes text at render time, so markup-like text is
kept as typed and shown literally. Prices are `Decimal` rupees (floats are rejected), and the whole
model is frozen and plain data, so `payload_from_model` can hash it for approvals.
"""

from decimal import Decimal
from typing import Annotated, Literal

from pydantic import (
    AfterValidator,
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
)

from app.engine.feasibility import Money
from app.schemas.text import is_plain_email, reject_control_characters

MAX_PRICE = Decimal("100000")
MAX_PRODUCTS = 12

Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
WEEK_ORDER: tuple[Weekday, ...] = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")

_CLEAN = AfterValidator(reject_control_characters)


def _line(min_length: int, max_length: int) -> StringConstraints:
    return StringConstraints(strip_whitespace=True, min_length=min_length, max_length=max_length)


Brand = Annotated[str, _line(1, 60), _CLEAN]
Tagline = Annotated[str, _line(1, 120), _CLEAN]
ProductName = Annotated[str, _line(1, 60), _CLEAN]
ProductDescription = Annotated[str, _line(0, 200), _CLEAN]
Description = Annotated[str, _line(0, 300), _CLEAN]
AvailabilityNote = Annotated[str, _line(0, 120), _CLEAN]
CapacityNote = Annotated[str, _line(1, 200), _CLEAN]
# Rupees, at most paise precision, never zero or negative, never a float (Money rejects floats).
ProductPrice = Annotated[Money, Field(gt=0, le=MAX_PRICE, decimal_places=2)]


class Product(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    name: ProductName
    description: ProductDescription = ""
    price: ProductPrice


class Availability(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    days: Annotated[list[Weekday], Field(min_length=1, max_length=7)]
    note: AvailabilityNote = ""

    @field_validator("days")
    @classmethod
    def _unique_and_in_week_order(cls, days: list[Weekday]) -> list[Weekday]:
        # Week order makes equal sets compare and hash equal, whatever order they arrived in.
        if len(set(days)) != len(days):
            raise ValueError("days must not repeat")
        return sorted(days, key=WEEK_ORDER.index)


def _plain_email(value: str) -> str:
    if not is_plain_email(value):
        raise ValueError("must be a plain email address")
    return value


ContactEmail = Annotated[str, _line(3, 254), _CLEAN, AfterValidator(_plain_email)]


class StorefrontConfig(BaseModel):
    """What a page shows. Tagline, availability and capacity are optional: a starter page never
    invents opening days or capacity for an owner, so it simply leaves them out."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    brand: Brand
    tagline: Tagline | None = None
    description: Description = ""
    products: Annotated[list[Product], Field(min_length=1, max_length=MAX_PRODUCTS)]
    availability: Availability | None = None
    capacity_note: CapacityNote | None = None
    # Shown as plain text, never as a link. None when the owner gave no address.
    contact_email: ContactEmail | None = None
    # Shows the FSSAI note on the page (set for food businesses).
    food_notice: bool = False
    contact_form_enabled: bool = False

    @field_validator("products")
    @classmethod
    def _product_names_are_unique(cls, products: list[Product]) -> list[Product]:
        names = [p.name.casefold() for p in products]
        if len(set(names)) != len(names):
            raise ValueError("product names must be unique")
        return products
