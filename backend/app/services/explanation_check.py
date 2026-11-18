"""The post-check on Claude's explanation. The engine's numbers are the only numbers allowed.

`validate_summary` returns None when the text is acceptable, or a short reason when it is not.
The reason is fed back to Claude on the one retry, so it never repeats anything it should not.
"""

import re
from decimal import Decimal, InvalidOperation
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, StringConstraints

from app.services.analyze_models import AnalyzeResponse
from app.services.explanation_facts import recommended_option

MIN_SENTENCES = 3
MAX_SENTENCES = 5
SCORE_SCALE = Decimal(100)  # "out of 100" is the scale of every score, so it is always allowed

_NUMBER = re.compile(r"(?<![\d.,])\d[\d,]*(?:\.\d+)?")
_DATASET_ID = re.compile(r"\b[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\b")
_SENTENCE_END = re.compile(r"(?<=[.!?])\s+")
_MARKUP = ("<", ">", "```", "](", "**")
_PROMISES = (
    "guarantee", "risk-free", "risk free", "will make money", "you will make", "certain to",
    "sure to profit", "cannot lose", "can't lose", "no risk",
)  # fmt: skip

# Spelled-out numbers are checked like digits. "one" is left out: it is mostly not a figure.
_SMALL = (
    "two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen "
    "sixteen seventeen eighteen nineteen twenty"
)
_WORDS = {
    **{word: Decimal(n) for n, word in enumerate(_SMALL.split(), start=2)},
    "thirty": Decimal(30), "forty": Decimal(40), "fifty": Decimal(50), "sixty": Decimal(60),
    "seventy": Decimal(70), "eighty": Decimal(80), "ninety": Decimal(90),
    "hundred": Decimal(100), "thousand": Decimal(1000), "lakh": Decimal(100_000),
    "million": Decimal(1_000_000), "crore": Decimal(10_000_000), "billion": Decimal(10**9),
}  # fmt: skip
_WORD_RE = re.compile(r"\b(" + "|".join(_WORDS) + r")\b", re.IGNORECASE)

# Dropped from the allowed set: dates and links that carry numbers but no figures.
_NOT_FIGURES: dict[str, Any] = {
    "analyzed_on": True,
    "steps": True,
    "evidence": {
        "__all__": {
            "source_url",
            "retrieved_date",
            "event_date",
            "verified_on",
            "verified_by",
            "lead_time_days",
        }  # fmt: skip
    },
}


class ExplanationOutput(BaseModel):
    """The only shape Claude may answer in."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    summary: Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=1500)]


def _numbers_in(text: str) -> list[Decimal]:
    found: list[Decimal] = []
    for raw in _NUMBER.findall(_DATASET_ID.sub(" ", text)):
        try:
            found.append(Decimal(raw.rstrip(",").replace(",", "")))
        except InvalidOperation:
            continue
    return found


def _walk(value: Any, into: set[Decimal]) -> None:
    if isinstance(value, bool) or value is None:
        return
    if isinstance(value, str):
        into.update(_numbers_in(value))
    elif isinstance(value, int | float):
        into.add(Decimal(str(value)))
    elif isinstance(value, dict):
        for item in value.values():
            _walk(item, into)
    elif isinstance(value, list):
        for item in value:
            _walk(item, into)


def allowed_numbers(analysis: AnalyzeResponse) -> set[Decimal]:
    allowed = {SCORE_SCALE, Decimal(len(analysis.options)), Decimal(len(analysis.ranking.ranked))}
    _walk(analysis.model_dump(mode="json", exclude=_NOT_FIGURES), allowed)
    return allowed


def _sentences(text: str) -> list[str]:
    return [s for s in _SENTENCE_END.split(text.strip()) if s.strip()]


def validate_summary(summary: str, analysis: AnalyzeResponse) -> str | None:
    count = len(_sentences(summary))
    if not MIN_SENTENCES <= count <= MAX_SENTENCES:
        return f"it must be 3 to 5 sentences, but it had {count}"
    if any(ord(c) < 32 for c in summary) or any(m in summary for m in _MARKUP):
        return "it must be plain text with no markup or control characters"
    lowered = summary.lower()
    if any(p in lowered for p in _PROMISES):
        return "it made a promise of profit, which is never allowed"
    allowed = allowed_numbers(analysis)
    for number in _numbers_in(summary):
        if number not in allowed:
            return f"it used the figure {number.normalize():f}, which is not in the facts"
    for match in _WORD_RE.finditer(summary):
        if _WORDS[match.group(1).lower()] not in allowed:
            return f"it used the number word '{match.group(1)}', which is not in the facts"
    known_ids = {e.id for e in analysis.evidence}
    for dataset_id in _DATASET_ID.findall(summary):
        if dataset_id not in known_ids:
            return f"it cited the dataset ID {dataset_id}, which is not in the facts"
    recommended = recommended_option(analysis)
    if recommended is not None and recommended.title.lower() not in lowered:
        return f"it must name the recommended option exactly: {recommended.title}"
    return None
