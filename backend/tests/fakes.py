"""Test doubles for injected collaborators."""

from datetime import UTC, datetime, timedelta


class FakeClock:
    """A clock that only moves when the test says so."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 11, 17, 10, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta
