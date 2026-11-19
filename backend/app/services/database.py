"""One SQLite connection for the app, shared by the page store and the approval audit log.

SQLite is a single file on the Docker volume (`/data`), so it survives restarts and rebuilds.
The app runs one worker, so one connection behind a lock is enough. Every statement is
parameterised: values never become part of the SQL text. `secure_delete` overwrites deleted
content, so a page that has been taken down does not linger in the file.
"""

import sqlite3
import threading
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from pathlib import Path
from typing import Any

MEMORY = ":memory:"


class Database:
    def __init__(self, path: str) -> None:
        if path != MEMORY:
            Path(path).expanduser().parent.mkdir(parents=True, exist_ok=True)
        # Autocommit; `transaction()` opens an explicit one when several statements go together.
        self._conn = sqlite3.connect(path, check_same_thread=False, isolation_level=None)
        self._lock = threading.RLock()
        with self._lock:
            self._conn.execute("PRAGMA secure_delete = ON")

    def script(self, sql: str) -> None:
        """Run fixed schema statements (never anything built from input)."""
        with self._lock:
            self._conn.executescript(sql)

    def query(self, sql: str, params: Sequence[Any] = ()) -> list[tuple[Any, ...]]:
        with self._lock:
            return self._conn.execute(sql, tuple(params)).fetchall()

    def execute(self, sql: str, params: Sequence[Any] = ()) -> int:
        """Run one statement and return how many rows it changed."""
        with self._lock:
            return self._conn.execute(sql, tuple(params)).rowcount

    @contextmanager
    def transaction(self) -> Iterator[None]:
        with self._lock:
            self._conn.execute("BEGIN IMMEDIATE")
            try:
                yield
            except BaseException:
                self._conn.execute("ROLLBACK")
                raise
            self._conn.execute("COMMIT")
