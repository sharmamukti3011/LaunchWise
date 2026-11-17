"""Transition table and payload hashing: the pure rules behind approvals."""

import itertools
from decimal import Decimal
from typing import Any

import pytest

from app.engine.approval_rules import (
    GATED_ACTIONS,
    TRANSITIONS,
    InvalidTransition,
    State,
    canonical_hash,
    check_transition,
)

S = State

ALLOWED = [
    (S.DRAFT, S.STRATEGY_PROPOSED),
    (S.STRATEGY_PROPOSED, S.STRATEGY_APPROVED),
    (S.STRATEGY_PROPOSED, S.DRAFT),
    (S.STRATEGY_APPROVED, S.LAUNCH_APPROVED),
    (S.STRATEGY_APPROVED, S.DRAFT),
    (S.LAUNCH_APPROVED, S.DEPLOYING),
    (S.DEPLOYING, S.LIVE),
    (S.DEPLOYING, S.FAILED),
]
FORBIDDEN = [pair for pair in itertools.product(State, State) if pair not in ALLOWED]


# ---- transition table -------------------------------------------------------------------------


def test_table_has_exactly_the_documented_transitions() -> None:
    actual = {(src, dst) for src, targets in TRANSITIONS.items() for dst in targets}
    assert actual == set(ALLOWED)


@pytest.mark.parametrize(("src", "dst"), ALLOWED)
def test_allowed_transition_passes(src: State, dst: State) -> None:
    check_transition(src, dst)


@pytest.mark.parametrize(("src", "dst"), FORBIDDEN)
def test_every_other_transition_raises(src: State, dst: State) -> None:
    with pytest.raises(InvalidTransition):
        check_transition(src, dst)


@pytest.mark.parametrize("terminal", [S.LIVE, S.FAILED])
def test_terminal_states_have_no_exits(terminal: State) -> None:
    assert TRANSITIONS[terminal] == frozenset()


def test_every_state_has_a_table_entry() -> None:
    assert set(TRANSITIONS) == set(State)


def test_only_the_two_approval_moves_are_gated() -> None:
    assert GATED_ACTIONS == {
        (S.STRATEGY_PROPOSED, S.STRATEGY_APPROVED): "approve_strategy",
        (S.STRATEGY_APPROVED, S.LAUNCH_APPROVED): "approve_launch",
    }
    assert set(GATED_ACTIONS) <= {(src, dst) for src, dst in ALLOWED}


# ---- canonical hash ---------------------------------------------------------------------------


def test_hash_is_a_sha256_hex_digest() -> None:
    digest = canonical_hash({"a": 1})
    assert len(digest) == 64
    assert set(digest) <= set("0123456789abcdef")


def test_hash_ignores_key_order_at_every_level() -> None:
    a = {"x": 1, "y": {"p": [1, 2], "q": "z"}}
    b = {"y": {"q": "z", "p": [1, 2]}, "x": 1}
    assert canonical_hash(a) == canonical_hash(b)


def test_hash_changes_when_any_value_changes() -> None:
    base = {"price": "800", "items": ["cake", "brownie"], "note": None}
    variants: list[dict[str, Any]] = [
        {**base, "price": "801"},
        {**base, "items": ["brownie", "cake"]},  # list order is meaningful
        {**base, "items": ["cake"]},
        {**base, "note": "x"},
        {**base, "extra": 1},
    ]
    digests = {canonical_hash(v) for v in variants} | {canonical_hash(base)}
    assert len(digests) == len(variants) + 1


def test_hash_distinguishes_types_that_look_alike() -> None:
    assert canonical_hash({"a": "1"}) != canonical_hash({"a": 1})
    assert canonical_hash({"a": True}) != canonical_hash({"a": 1})


def test_hash_handles_unicode_text() -> None:
    assert canonical_hash({"t": "₹800 पुणे"}) == canonical_hash({"t": "₹800 पुणे"})
    assert canonical_hash({"t": "₹800"}) != canonical_hash({"t": "Rs800"})


@pytest.mark.parametrize(
    ("left", "right"),
    [("1.50", "1.5"), ("100", "1E+2"), ("0.00", "0"), ("-0", "0"), ("2.500", "2.5")],
)
def test_decimal_values_that_are_equal_hash_the_same(left: str, right: str) -> None:
    assert canonical_hash({"price": Decimal(left)}) == canonical_hash({"price": Decimal(right)})


def test_decimal_values_that_differ_hash_differently() -> None:
    assert canonical_hash({"p": Decimal("1.5")}) != canonical_hash({"p": Decimal("1.51")})


def test_decimal_inside_nested_structures_is_normalised() -> None:
    a = {"lines": [{"amount": Decimal("10.0")}]}
    b = {"lines": [{"amount": Decimal("10")}]}
    assert canonical_hash(a) == canonical_hash(b)


def test_tuples_hash_like_lists() -> None:
    assert canonical_hash({"a": (1, 2)}) == canonical_hash({"a": [1, 2]})


@pytest.mark.parametrize("bad", [1.5, float("nan")])
def test_float_anywhere_is_rejected(bad: float) -> None:
    with pytest.raises(TypeError, match="float"):
        canonical_hash({"outer": [{"price": bad}]})


@pytest.mark.parametrize("bad", [Decimal("NaN"), Decimal("Infinity")])
def test_non_finite_decimal_is_rejected(bad: Decimal) -> None:
    with pytest.raises(ValueError, match="finite"):
        canonical_hash({"p": bad})


def test_unsupported_types_and_non_string_keys_are_rejected() -> None:
    with pytest.raises(TypeError):
        canonical_hash({"when": object()})
    with pytest.raises(TypeError):
        canonical_hash({1: "a"})
