"""Test doubles for injected collaborators."""

from collections.abc import Callable
from datetime import UTC, datetime, timedelta

from app.services.approvals import LaunchPayload


class FakeClock:
    """A clock that only moves when the test says so."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 11, 17, 10, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


class FakeDeployer:
    """Records every deploy call. `on_call` lets a test inspect the world at call time."""

    def __init__(
        self,
        fail_with: Exception | None = None,
        on_call: Callable[[str, LaunchPayload], None] | None = None,
    ) -> None:
        self.calls: list[tuple[str, LaunchPayload]] = []
        self._fail_with = fail_with
        self._on_call = on_call

    def deploy(self, run_id: str, payload: LaunchPayload) -> None:
        self.calls.append((run_id, payload))
        if self._on_call is not None:
            self._on_call(run_id, payload)
        if self._fail_with is not None:
            raise self._fail_with
