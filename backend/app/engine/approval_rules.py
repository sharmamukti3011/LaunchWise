"""Pure approval rules: the transition table and the payload hash. No clock, no state, no I/O."""

import hashlib
import json
from decimal import Decimal
from enum import StrEnum
from typing import Any


class State(StrEnum):
    DRAFT = "DRAFT"
    STRATEGY_PROPOSED = "STRATEGY_PROPOSED"
    STRATEGY_APPROVED = "STRATEGY_APPROVED"
    LAUNCH_APPROVED = "LAUNCH_APPROVED"
    DEPLOYING = "DEPLOYING"
    LIVE = "LIVE"
    FAILED = "FAILED"


class InvalidTransition(Exception):
    """The requested move is not in the transition table."""

    def __init__(self, src: State, dst: State) -> None:
        super().__init__(f"transition {src.value} -> {dst.value} is not allowed")
        self.src = src
        self.dst = dst


# The single source of truth. LIVE and FAILED are terminal: a retry starts a fresh run.
# The two back-edges to DRAFT let a rejected or revised strategy restart the flow.
TRANSITIONS: dict[State, frozenset[State]] = {
    State.DRAFT: frozenset({State.STRATEGY_PROPOSED}),
    State.STRATEGY_PROPOSED: frozenset({State.STRATEGY_APPROVED, State.DRAFT}),
    State.STRATEGY_APPROVED: frozenset({State.LAUNCH_APPROVED, State.DRAFT}),
    State.LAUNCH_APPROVED: frozenset({State.DEPLOYING}),
    State.DEPLOYING: frozenset({State.LIVE, State.FAILED}),
    State.LIVE: frozenset(),
    State.FAILED: frozenset(),
}

# Moves that need a granted approval, and the action name that approval must carry.
# DEPLOYING is not listed: it consumes the launch approval via the deploy guard instead.
GATED_ACTIONS: dict[tuple[State, State], str] = {
    (State.STRATEGY_PROPOSED, State.STRATEGY_APPROVED): "approve_strategy",
    (State.STRATEGY_APPROVED, State.LAUNCH_APPROVED): "approve_launch",
}


def check_transition(src: State, dst: State) -> None:
    """Raise `InvalidTransition` unless `src -> dst` is in the table."""
    if dst not in TRANSITIONS[src]:
        raise InvalidTransition(src, dst)


def _normalise_decimal(value: Decimal) -> str:
    if not value.is_finite():
        raise ValueError(f"only finite Decimal values can be hashed, got {value}")
    if value == 0:
        return "0"  # also folds -0 and 0.00
    # 'f' avoids exponent notation, so Decimal("1E+2") and Decimal("100") agree.
    return format(value.normalize(), "f")


def _canonical(value: Any) -> Any:
    if value is None or isinstance(value, bool | int | str):
        return value
    if isinstance(value, float):
        raise TypeError("float is not allowed in an approved payload; use Decimal or integer paise")
    if isinstance(value, Decimal):
        # Tagged so a Decimal never collides with a plain string like "1.5".
        return {"__decimal__": _normalise_decimal(value)}
    if isinstance(value, dict):
        out: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError(f"payload keys must be strings, got {type(key).__name__}")
            out[key] = _canonical(item)
        return out
    if isinstance(value, list | tuple):
        return [_canonical(item) for item in value]
    raise TypeError(f"unsupported type in approved payload: {type(value).__name__}")


def canonical_hash(payload: Any) -> str:
    """sha256 hex of the payload's canonical JSON: sorted keys, no whitespace, UTF-8.

    Changing any value, key or list order changes the hash. Key order does not.
    """
    text = json.dumps(
        _canonical(payload), sort_keys=True, separators=(",", ":"), ensure_ascii=False
    )
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
