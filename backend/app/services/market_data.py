"""The market dataset: loading, startup validation, and coverage matching.

The dataset is hand-curated Pune bakery evidence (see docs/SPEC.md). It lives inside the app
package (`app/data/`) so the Docker image, which copies only `backend/app`, ships it. Loading is
strict on purpose: the app calls `load_dataset` at startup and refuses to boot on bad data.

Coverage is a plain question, "does the dataset have evidence for this place and business?". When
the answer is no, callers must not invent evidence; they fall back to a feasibility-only analysis.
"""

import json
from collections.abc import Iterable
from pathlib import Path
from typing import Any

from pydantic import BaseModel, ConfigDict, ValidationError

from app.services.strategy_models import EvidenceDirection, Opportunity

DATASET_PATH = Path(__file__).resolve().parents[1] / "data" / "market_opportunities.json"
MAX_DATASET_BYTES = 256 * 1024

# Trailing words that name a region, not a different place: "Pune, Maharashtra" is still Pune.
_REGION_WORDS = {"city", "district", "maharashtra", "india"}


class EvidenceChoice(BaseModel):
    """What a picker needs to offer a dataset entry: never the evidence text or the link."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    source_name: str
    direction: EvidenceDirection


class EvidenceChoiceList(BaseModel):
    model_config = ConfigDict(frozen=True)

    evidence: list[EvidenceChoice]


class DatasetError(Exception):
    """The dataset file is missing, malformed, or holds an invalid entry."""


def normalise_place(value: str) -> str:
    """Lower-case, trimmed, first comma segment, region words dropped.

    'Pune, Maharashtra' and ' PUNE City ' both become 'pune'.
    """
    first = value.split(",", 1)[0].casefold().split()
    while len(first) > 1 and first[-1] in _REGION_WORDS:
        first.pop()
    return " ".join(first)


def _normalise_category(value: str) -> str:
    return " ".join(value.casefold().split())


def _category_matches(entry_category: str, requested: str) -> bool:
    entry, wanted = _normalise_category(entry_category), _normalise_category(requested)
    if not entry or not wanted:
        return False
    # "home bakery" is a bakery; "high-protein breakfast" is not.
    return entry in wanted or wanted in entry


class MarketDataset:
    """An immutable, id-unique collection of opportunities."""

    def __init__(self, opportunities: Iterable[Opportunity]) -> None:
        items = tuple(opportunities)
        ids = [o.id for o in items]
        for duplicate in sorted({i for i in ids if ids.count(i) > 1}):
            raise DatasetError(f"duplicate opportunity id {duplicate!r}")
        self._items = items
        self._by_id = {o.id: o for o in items}

    @property
    def opportunities(self) -> tuple[Opportunity, ...]:
        return self._items

    def ids(self) -> frozenset[str]:
        return frozenset(self._by_id)

    def get(self, opportunity_id: str) -> Opportunity | None:
        return self._by_id.get(opportunity_id)

    def choices(self) -> EvidenceChoiceList:
        return EvidenceChoiceList(
            evidence=[
                EvidenceChoice(
                    id=o.id, title=o.title, source_name=o.source_name, direction=o.direction
                )
                for o in self._items
            ]
        )

    def covers(self, location: str, category: str) -> bool:
        """True if some entry is for this place and this kind of business."""
        place = normalise_place(location)
        if not place:
            return False
        return any(
            normalise_place(o.location) == place and _category_matches(o.category, category)
            for o in self._items
        )


def _read_json(path: Path) -> Any:
    try:
        size = path.stat().st_size
    except FileNotFoundError:
        raise DatasetError(f"dataset file not found: {path.name}") from None
    if size > MAX_DATASET_BYTES:
        raise DatasetError(f"dataset file is too large ({size} bytes, limit {MAX_DATASET_BYTES})")
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise DatasetError(f"dataset file is not valid JSON ({type(exc).__name__})") from None


def _validate_entry(position: int, raw: Any) -> Opportunity:
    label = f"entry {position}"
    if not isinstance(raw, dict):
        raise DatasetError(f"{label} is not an object")
    label += f" ({raw.get('id', '?')})"
    unknown = sorted(set(raw) - set(Opportunity.model_fields))
    if unknown:
        # Opportunity ignores unknown keys, so a typo like "verfied_by" would silently drop a rule.
        raise DatasetError(f"{label}: unknown field(s): {', '.join(unknown)}")
    try:
        return Opportunity.model_validate(raw)
    except ValidationError as exc:
        # Field names and rule messages only. Never the submitted values.
        problems = "; ".join(
            f"{'.'.join(str(p) for p in err['loc']) or 'entry'}: {err['msg']}"
            for err in exc.errors(include_input=False)
        )
        raise DatasetError(f"{label}: {problems}") from None


def load_dataset(path: Path = DATASET_PATH) -> MarketDataset:
    """Load and fully validate the dataset, or raise `DatasetError`."""
    data = _read_json(path)
    if not isinstance(data, dict) or not isinstance(data.get("opportunities"), list):
        raise DatasetError('dataset must be an object with an "opportunities" list')
    if not data["opportunities"]:
        raise DatasetError("dataset has no opportunities")
    return MarketDataset(_validate_entry(i, raw) for i, raw in enumerate(data["opportunities"], 1))
