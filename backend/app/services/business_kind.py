"""Does this business sell food? Decides whether the FSSAI note is shown.

Plain whole-word keyword rules on text the owner typed, so the answer is deterministic and easy
to test. It errs towards showing the note: a missed food business matters more than an extra
reminder. Pure, with no I/O, and it never reads more than the first few hundred characters.
"""

import re

MAX_CHARS = 500

# Matched as whole words, with an optional plural. "tea" never matches "team" or "teaching".
_WORDS = [
    "cake",
    "cookie",
    "biscuit",
    "bread",
    "pastry",
    "pie",
    "dessert",
    "sweet",
    "mithai",
    "chocolate",
    "candy",
    "snack",
    "namkeen",
    "pickle",
    "jam",
    "sauce",
    "juice",
    "tea",
    "chai",
    "coffee",
    "beverage",
    "food",
    "meal",
    "tiffin",
    "kitchen",
    "restaurant",
    "cafe",
    "café",
    "breakfast",
    "lunch",
    "dinner",
    "dairy",
    "paneer",
    "curd",
    "ghee",
    "spice",
    "masala",
    "sandwich",
    "burger",
    "pizza",
    "noodle",
    "momo",
    "samosa",
    "laddu",
    "ladoo",
    "popcorn",
]
# Word starts that cover their own forms: bakery, bakeries, baking, baker; catering, caterer.
_STEMS = ("bak", "cater")

_STEM_PATTERN = "|".join(f"{stem}\\w*" for stem in _STEMS)
_WORD_PATTERN = "(?:" + "|".join(_WORDS) + ")(?:s|es)?"
_FOOD = re.compile(rf"\b(?:{_STEM_PATTERN}|{_WORD_PATTERN})\b", re.IGNORECASE)


def is_food_business(text: str) -> bool:
    return _FOOD.search(text[:MAX_CHARS]) is not None
