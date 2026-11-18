"""The one Clock protocol. Services take a clock instead of calling datetime.now() themselves,
so tests can move time by hand."""

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


class SystemClock:
    def now(self) -> datetime:
        return datetime.now(UTC)
