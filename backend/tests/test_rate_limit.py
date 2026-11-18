"""RateLimiter: sliding window per key, with an injected clock."""

import sys
import threading
from datetime import timedelta

import pytest

from app.services.rate_limit import RateLimited, RateLimiter
from tests.fakes import FakeClock

WINDOW = timedelta(minutes=10)
SECOND = timedelta(seconds=1)


def limiter(clock: FakeClock, limit: int = 3, **kwargs: int) -> RateLimiter:
    return RateLimiter(limit=limit, window=WINDOW, clock=clock, **kwargs)


def test_allows_up_to_the_limit_then_refuses() -> None:
    rl = limiter(FakeClock())
    for _ in range(3):
        rl.check("a")
    with pytest.raises(RateLimited):
        rl.check("a")


def test_retry_after_is_the_whole_seconds_until_the_oldest_hit_expires() -> None:
    clock = FakeClock()
    rl = limiter(clock)
    rl.check("a")  # t0: this is the hit that frees a slot first
    clock.advance(10 * SECOND)
    rl.check("a")
    clock.advance(10 * SECOND)
    rl.check("a")
    clock.advance(10 * SECOND)  # t0 + 30s
    with pytest.raises(RateLimited) as refused:
        rl.check("a")
    assert refused.value.retry_after == 570  # 600s window minus 30s


def test_retry_after_rounds_up_and_is_at_least_one_second() -> None:
    clock = FakeClock()
    rl = limiter(clock, limit=1)
    rl.check("a")
    clock.advance(WINDOW - timedelta(milliseconds=200))
    with pytest.raises(RateLimited) as refused:
        rl.check("a")
    assert refused.value.retry_after == 1


def test_window_edge_one_second_before_still_blocked_exactly_at_window_allowed() -> None:
    clock = FakeClock()
    rl = limiter(clock, limit=1)
    rl.check("a")
    clock.advance(WINDOW - SECOND)
    with pytest.raises(RateLimited):
        rl.check("a")
    clock.advance(SECOND)  # exactly one window after the hit
    rl.check("a")


def test_window_slides_one_slot_at_a_time() -> None:
    clock = FakeClock()
    rl = limiter(clock)
    rl.check("a")  # t0
    clock.advance(5 * SECOND)
    rl.check("a")  # t0+5
    rl.check("a")  # t0+5
    clock.advance(WINDOW - 5 * SECOND)  # t0 + window: only the first hit has expired
    rl.check("a")
    with pytest.raises(RateLimited):
        rl.check("a")


def test_refused_attempts_do_not_extend_the_block() -> None:
    clock = FakeClock()
    rl = limiter(clock, limit=1)
    rl.check("a")
    for _ in range(5):
        clock.advance(60 * SECOND)
        with pytest.raises(RateLimited):
            rl.check("a")
    clock.advance(WINDOW)  # well past the one real hit
    rl.check("a")


def test_clients_have_independent_buckets() -> None:
    # Different visitor addresses must never share a bucket (nor collapse into the proxy's IP).
    rl = limiter(FakeClock())
    for _ in range(3):
        rl.check("198.51.100.1")
    with pytest.raises(RateLimited):
        rl.check("198.51.100.1")
    for address in ("198.51.100.2", "203.0.113.5", "10.77.0.10"):
        for _ in range(3):
            rl.check(address)
        with pytest.raises(RateLimited):
            rl.check(address)


def test_expired_keys_are_forgotten() -> None:
    clock = FakeClock()
    rl = limiter(clock)
    for key in ("a", "b", "c"):
        rl.check(key)
    assert len(rl) == 3
    clock.advance(WINDOW)
    rl.check("d")  # any call cleans up the expired ones
    assert len(rl) == 1


def test_key_count_is_bounded_by_evicting_the_least_recently_used() -> None:
    clock = FakeClock()
    rl = limiter(clock, limit=1, max_keys=3)
    for key in ("a", "b", "c"):
        rl.check(key)
        clock.advance(SECOND)
    rl.check("d")  # full: "a", the least recently used, makes room
    assert len(rl) == 3
    rl.check("a")  # "a" was forgotten, so it starts fresh instead of being refused
    with pytest.raises(RateLimited):
        rl.check("d")  # "d" is still tracked


def test_many_distinct_keys_never_grow_memory_past_the_cap() -> None:
    rl = limiter(FakeClock(), limit=1, max_keys=50)
    for i in range(500):
        rl.check(f"10.0.{i // 250}.{i % 250}")
    assert len(rl) <= 50


@pytest.mark.parametrize(("limit", "window"), [(0, WINDOW), (-1, WINDOW), (1, timedelta(0))])
def test_rejects_nonsense_configuration(limit: int, window: timedelta) -> None:
    with pytest.raises(ValueError, match="must be"):
        RateLimiter(limit=limit, window=window, clock=FakeClock())


def test_max_keys_must_be_positive() -> None:
    with pytest.raises(ValueError, match="max_keys"):
        RateLimiter(limit=1, window=WINDOW, clock=FakeClock(), max_keys=0)


def test_concurrent_checks_on_one_key_admit_exactly_the_limit() -> None:
    # Forcing very frequent thread switches makes an unlocked check-then-record race show up
    # reliably, over many rounds. (Verified: this fails when the lock is removed.)
    threads, rounds = 20, 150
    previous = sys.getswitchinterval()
    sys.setswitchinterval(1e-6)
    try:
        for _ in range(rounds):
            rl = RateLimiter(limit=5, window=WINDOW, clock=FakeClock())
            barrier = threading.Barrier(threads)
            outcomes: list[str] = []

            def attempt(
                rl: RateLimiter = rl,
                barrier: threading.Barrier = barrier,
                outcomes: list[str] = outcomes,
            ) -> None:
                barrier.wait()
                try:
                    rl.check("a")
                    outcomes.append("ok")
                except RateLimited:
                    outcomes.append("limited")

            workers = [threading.Thread(target=attempt) for _ in range(threads)]
            for worker in workers:
                worker.start()
            for worker in workers:
                worker.join()
            assert outcomes.count("ok") == 5
            assert outcomes.count("limited") == threads - 5
    finally:
        sys.setswitchinterval(previous)
