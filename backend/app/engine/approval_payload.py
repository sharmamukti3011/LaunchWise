"""The one definition of "the exact payload" an approval is bound to.

Every caller (request, decide, transition, consume) turns its Pydantic model into a hashable
payload through `payload_from_model`, so the same content can never hash two different ways.
"""

from collections.abc import Iterable
from datetime import date
from enum import Enum
from typing import Any

from pydantic import AnyUrl, BaseModel

from app.engine.approval_rules import canonical_hash

# Lists with these names are really sets: order carries no meaning, so sort before hashing.
# Add a name here (not at call sites) when another set-like field appears in an approved model.
SET_LIKE_FIELDS = frozenset({"skills", "equipment", "required_skills", "required_equipment"})


def _as_sorted_set(items: Iterable[Any]) -> list[Any]:
    plain = [_plain(item) for item in items]
    if all(isinstance(item, str) for item in plain):
        return sorted(set(plain))
    # Mixed or structured members: order by their own canonical hash, which is deterministic.
    unique = {canonical_hash(item): item for item in plain}
    return [unique[digest] for digest in sorted(unique)]


def _plain(value: Any, key: str | None = None) -> Any:
    """Reduce a `model_dump()` value to plain data. Decimals stay Decimal; the hash normalises."""
    if isinstance(value, Enum):
        return _plain(value.value, key)
    if isinstance(value, date):  # also covers datetime
        return value.isoformat()
    if isinstance(value, AnyUrl):
        return str(value)
    if isinstance(value, dict):
        return {k: _plain(v, k if isinstance(k, str) else None) for k, v in value.items()}
    if isinstance(value, set | frozenset):
        return _as_sorted_set(value)
    if isinstance(value, list | tuple):
        if key in SET_LIKE_FIELDS:
            return _as_sorted_set(value)
        return [_plain(item) for item in value]
    return value  # str, int, bool, None, Decimal; anything else is rejected by canonical_hash


def payload_from_model(model: BaseModel) -> dict[str, Any]:
    """The plain-data payload for `model`: dates as ISO text, enums as values, sets sorted."""
    result: dict[str, Any] = _plain(model.model_dump(mode="python"))
    return result


def hash_model(model: BaseModel) -> str:
    """sha256 of the model's payload. The only way services compute an approval hash."""
    return canonical_hash(payload_from_model(model))
