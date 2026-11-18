"""The post-check on Claude's draft: every number in it must appear in the owner's description.

"₹10,000", "10000", "10k", "ten thousand" and "10 thousand" are the same number. A number the
owner did not write (a guess, a sum, "weekends only" read as 2 days) is rejected, so the draft
can only repeat figures the owner stated.
"""

import re
import unicodedata
from decimal import Decimal

from app.services.intake_models import ClaudeDraft

_MULTIPLIERS = {
    "k": 1_000,
    "thousand": 1_000,
    "lakh": 100_000,
    "lakhs": 100_000,
    "lac": 100_000,
    "lacs": 100_000,
    "crore": 10_000_000,
    "crores": 10_000_000,
    "million": 1_000_000,
}
# A digit run, optionally followed by a multiplier word: 10k, 1.5 lakh, 2 crore, 10 thousand.
_DIGITS = re.compile(
    r"(?<![\d.,])(\d[\d,]*(?:\.\d+)?)(?:\s*(k|thousand|lakhs?|lacs?|crores?|million)\b)?"
)

_UNITS = [
    "zero",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
    "eleven",
    "twelve",
    "thirteen",
    "fourteen",
    "fifteen",
    "sixteen",
    "seventeen",
    "eighteen",
    "nineteen",
]
_TENS = ["twenty", "thirty", "forty", "fifty", "sixty", "seventy", "eighty", "ninety"]
_SMALL = {word: n for n, word in enumerate(_UNITS)} | {
    word: 20 + 10 * n for n, word in enumerate(_TENS)
}
_BIG = {"thousand": 1_000, "lakh": 100_000, "lakhs": 100_000, "lac": 100_000, "lacs": 100_000,
        "crore": 10_000_000, "crores": 10_000_000, "million": 1_000_000}  # fmt: skip
_WORD = re.compile(r"[a-z]+")


def _digit_numbers(text: str) -> list[Decimal]:
    found: list[Decimal] = []
    for raw, multiplier in _DIGITS.findall(text):
        base = Decimal(raw.rstrip(",").replace(",", ""))
        found.append(base)
        if multiplier:
            found.append(base * _MULTIPLIERS[multiplier])
    return found


def _word_numbers(text: str) -> list[Decimal]:
    """Numbers written in words: 'three', 'twenty-five', 'ten thousand', 'one lakh'."""
    found: list[Decimal] = []
    total = current = 0
    started = False

    def finish() -> None:
        nonlocal total, current, started
        if started:
            found.append(Decimal(total + current))
        total = current = 0
        started = False

    for word in _WORD.findall(text):
        if word in _SMALL:
            current += _SMALL[word]
            started = True
        elif word == "hundred":
            current = max(current, 1) * 100
            started = True
        elif word in _BIG:
            total += max(current, 1) * _BIG[word]
            current = 0
            started = True
        elif word == "and" and started:
            continue
        else:
            finish()
    finish()
    return found


def numbers_in_text(text: str) -> set[Decimal]:
    lowered = unicodedata.normalize("NFKC", text).lower()
    return set(_digit_numbers(lowered)) | set(_word_numbers(lowered))


def _leaves(draft: ClaudeDraft) -> list[str]:
    values: list[str | list[str] | None] = [
        draft.budget,
        draft.units_per_day,
        draft.days_per_week,
        draft.hours_per_week,
        draft.skills,
        draft.equipment,
        draft.location,
        draft.category,
    ]
    for option in (draft.original, draft.alternative):
        if option is not None:
            values += [option.title, option.price, option.cost, option.startup, option.minutes]
    leaves: list[str] = []
    for value in values:
        if isinstance(value, list):
            leaves += value
        elif value is not None:
            leaves.append(value)
    return leaves


def numbers_in_draft(draft: ClaudeDraft) -> set[Decimal]:
    found: set[Decimal] = set()
    for leaf in _leaves(draft):
        found.update(_digit_numbers(leaf))
    return found


def check_draft(draft: ClaudeDraft, text: str) -> str | None:
    """None when every number in the draft is in the description, else the reason."""
    allowed = numbers_in_text(text)
    for leaf in _leaves(draft):
        for number in _digit_numbers(leaf):
            if number not in allowed:
                return f"it used the number {number.normalize():f}, which is not in the description"
    return None
