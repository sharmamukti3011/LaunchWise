"""The request for a starter page, and how it becomes a StorefrontConfig.

Everything here is text an owner types for a PUBLIC page, so it is held to stricter rules than the
analysis form: no markup, no links, no emails or handles in free text, and a small blocklist. A
refusal carries only a fixed code, never the reason or the matching word.
"""

from decimal import Decimal
from typing import Annotated, Any

from pydantic import AfterValidator, BaseModel, BeforeValidator, ConfigDict, StringConstraints

from app.schemas.storefront import (
    ContactEmail,
    Product,
    ProductPrice,
    StorefrontConfig,
)
from app.schemas.text import reject_control_characters
from app.services.content_rules import contains_markup_or_link, is_blocked

NO_LINKS = "no_links_or_markup"
NOT_ALLOWED = "not_allowed"


def _public_text(value: str) -> str:
    reject_control_characters(value)
    if contains_markup_or_link(value):
        raise ValueError(NO_LINKS)
    if is_blocked(value):
        raise ValueError(NOT_ALLOWED)
    return value


def _blank_to_none(value: Any) -> Any:
    return None if isinstance(value, str) and not value.strip() else value


def _none_to_empty(value: Any) -> Any:
    return "" if value is None else value


_CHECKED = AfterValidator(_public_text)
BusinessName = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60), _CHECKED
]
OfferTitle = Annotated[
    str, StringConstraints(strip_whitespace=True, min_length=1, max_length=60), _CHECKED
]
ShortDescription = Annotated[
    str,
    BeforeValidator(_none_to_empty),
    StringConstraints(strip_whitespace=True, min_length=0, max_length=300),
    _CHECKED,
]
OptionalEmail = Annotated[ContactEmail | None, BeforeValidator(_blank_to_none)]


class StarterPageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    business_name: BusinessName
    description: ShortDescription = ""
    contact_email: OptionalEmail = None
    offer_title: OfferTitle
    offer_price: ProductPrice
    food_business: bool = False


def to_config(request: StarterPageRequest) -> StorefrontConfig:
    """The page content, and nothing the owner did not give: no opening days, no capacity."""
    price: Decimal = request.offer_price
    return StorefrontConfig(
        brand=request.business_name,
        description=request.description,
        products=[Product(name=request.offer_title, price=price)],
        contact_email=request.contact_email,
        food_notice=request.food_business,
    )
