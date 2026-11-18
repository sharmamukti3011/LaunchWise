"""The shared Clock protocol: one definition, usable by approvals, the rate limiter and fakes."""

from datetime import UTC, datetime, timedelta

from app.services import approvals
from app.services.clock import Clock, SystemClock
from tests.fakes import FakeClock


def test_system_clock_returns_timezone_aware_utc_now() -> None:
    before = datetime.now(UTC)
    reading = SystemClock().now()
    after = datetime.now(UTC)
    assert reading.tzinfo is not None and reading.utcoffset() == timedelta(0)
    assert before <= reading <= after


def test_fake_clock_satisfies_the_protocol() -> None:
    clock: Clock = FakeClock()  # mypy checks the structural match
    assert clock.now().tzinfo is not None


def test_approvals_still_exposes_the_same_clock_types() -> None:
    # The move must not break existing imports.
    assert approvals.Clock is Clock
    assert approvals.SystemClock is SystemClock
