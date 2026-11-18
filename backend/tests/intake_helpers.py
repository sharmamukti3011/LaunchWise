"""Shared builders for the Intake tests."""

import json
from typing import Any

# The owner's description. Every number here is written by the owner.
TEXT = (
    "I run a small home bakery in Pune. I have ₹10,000 to start, and I can make about 3 cakes "
    "per day on weekends only. Everyday cakes sell for ₹500 and cost me ₹450 to make, with "
    "₹3,000 of startup costs. I could also try custom celebration cakes at ₹1,400 each costing "
    "₹500, with ₹4,000 setup."
)


def draft_dict(**overrides: Any) -> dict[str, Any]:
    """What Claude should answer for TEXT: only what the text states, everything else null."""
    data: dict[str, Any] = {
        "budget": "10000",
        "units_per_day": "3",
        "days_per_week": None,  # "weekends only" is not a number, so it is not guessed
        "hours_per_week": None,
        "skills": None,
        "equipment": None,
        "location": "Pune",
        "category": "home bakery",
        "original": {
            "title": "Everyday cakes",
            "price": "500",
            "cost": "450",
            "startup": "3000",
            "minutes": None,
        },
        "alternative": {
            "title": "Custom celebration cakes",
            "price": "1400",
            "cost": "500",
            "startup": "4000",
            "minutes": None,
        },
    }
    data.update(overrides)
    return data


def draft_reply(**overrides: Any) -> str:
    return json.dumps(draft_dict(**overrides))


def empty_reply() -> str:
    """A valid answer that states nothing: every field null. It has no numbers to check."""
    blank = {"title": None, "price": None, "cost": None, "startup": None, "minutes": None}
    data = {k: None for k in draft_dict()} | {"original": blank, "alternative": None}
    return json.dumps(data)
