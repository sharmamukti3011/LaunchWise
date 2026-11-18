"""Sliding-window rate limiter, one bucket per key (for the contact form, the client address).

Pure in-process logic with an injected clock. State is per process, which is right for the single
backend container; a multi-instance deployment would need a shared store.
"""

import math
import threading
from collections import OrderedDict, deque
from datetime import datetime, timedelta

from app.services.clock import Clock

DEFAULT_MAX_KEYS = 10_000


class RateLimited(Exception):
    """The key used up its quota. `retry_after` is whole seconds, at least 1."""

    def __init__(self, retry_after: int) -> None:
        super().__init__(f"rate limited, retry after {retry_after}s")
        self.retry_after = retry_after


class RateLimiter:
    """Allows `limit` hits per `window` for each key. Keys never share a bucket.

    A hit at time t counts until t + window; at exactly t + window it is expired. Refused
    attempts are not recorded, so hammering a blocked key does not extend the block.
    """

    def __init__(
        self, *, limit: int, window: timedelta, clock: Clock, max_keys: int = DEFAULT_MAX_KEYS
    ) -> None:
        if limit < 1:
            raise ValueError("limit must be at least 1")
        if window <= timedelta(0):
            raise ValueError("window must be positive")
        if max_keys < 1:
            raise ValueError("max_keys must be at least 1")
        self._limit = limit
        self._window = window
        self._clock = clock
        self._max_keys = max_keys
        self._lock = threading.Lock()
        # Least recently used first, so eviction under a flood of new keys is O(1).
        self._hits: OrderedDict[str, deque[datetime]] = OrderedDict()
        self._next_sweep = clock.now() + window

    def __len__(self) -> int:
        with self._lock:
            return len(self._hits)

    def check(self, key: str) -> None:
        """Record a hit for `key`, or raise `RateLimited`. Check and record are atomic."""
        with self._lock:
            now = self._clock.now()
            self._sweep(now)
            hits = self._hits.get(key)
            if hits is None:
                self._make_room()
                hits = self._hits[key] = deque()
            else:
                self._hits.move_to_end(key)
            self._expire(hits, now)
            if len(hits) >= self._limit:
                wait = (hits[0] + self._window - now).total_seconds()
                raise RateLimited(max(1, math.ceil(wait)))
            hits.append(now)

    def _expire(self, hits: deque[datetime], now: datetime) -> None:
        cutoff = now - self._window
        while hits and hits[0] <= cutoff:
            hits.popleft()

    def _sweep(self, now: datetime) -> None:
        """Forget keys whose hits all expired. Runs at most once per window to keep checks cheap."""
        if now < self._next_sweep:
            return
        self._next_sweep = now + self._window
        for key in list(self._hits):
            self._expire(self._hits[key], now)
            if not self._hits[key]:
                del self._hits[key]

    def _make_room(self) -> None:
        # A flood of distinct addresses must not grow memory without bound.
        while len(self._hits) >= self._max_keys:
            self._hits.popitem(last=False)
