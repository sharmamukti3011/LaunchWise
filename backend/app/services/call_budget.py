"""Caps on Claude calls: one total for the whole app and one per visitor ("session").

There are no accounts, so a session is the visitor's address, the same key the rate limiters
use. Counts live for the life of the process, so a restart resets them; the caps are a cost
guard, not a quota. Pure in-process logic, no clock needed.
"""

import threading
from collections import OrderedDict


class CallBudget:
    def __init__(self, *, per_key: int, total: int, max_keys: int = 10_000) -> None:
        if per_key < 1 or total < 1 or max_keys < 1:
            raise ValueError("per_key, total and max_keys must be at least 1")
        self._per_key = per_key
        self._total = total
        self._max_keys = max_keys
        self._used_total = 0
        self._used: OrderedDict[str, int] = OrderedDict()
        self._lock = threading.Lock()

    def __len__(self) -> int:
        with self._lock:
            return len(self._used)

    def reserve(self, key: str) -> bool:
        """Spend one call for `key`. False, and nothing spent, when either cap is reached."""
        with self._lock:
            if self._used_total >= self._total:
                return False
            used = self._used.get(key, 0)
            if used >= self._per_key:
                return False
            self._used_total += 1
            self._used[key] = used + 1
            self._used.move_to_end(key)
            # A flood of distinct addresses must not grow memory without bound. Forgetting the
            # oldest visitor only gives them a fresh allowance; the total cap still holds.
            while len(self._used) > self._max_keys:
                self._used.popitem(last=False)
            return True
