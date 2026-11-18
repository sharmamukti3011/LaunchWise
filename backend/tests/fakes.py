"""Test doubles for injected collaborators."""

import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from app.services.approvals import LaunchPayload


class FakeClock:
    """A clock that only moves when the test says so."""

    def __init__(self, start: datetime | None = None) -> None:
        self._now = start or datetime(2026, 11, 17, 10, 0, tzinfo=UTC)

    def now(self) -> datetime:
        return self._now

    def advance(self, delta: timedelta) -> None:
        self._now += delta


class SlowClock(FakeClock):
    """Sleeps on every read, widening any gap between 'check' and 'record' so a missing lock
    shows up as a failing concurrency test instead of passing by luck."""

    def now(self) -> datetime:
        time.sleep(0.002)
        return super().now()


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


class FakeMailSender:
    """Collects messages instead of sending them. `fail_with` simulates a delivery failure."""

    def __init__(self, fail_with: Exception | None = None) -> None:
        self.sent: list[EmailMessage] = []
        self._fail_with = fail_with

    def send(self, message: EmailMessage) -> None:
        if self._fail_with is not None:
            raise self._fail_with
        self.sent.append(message)
