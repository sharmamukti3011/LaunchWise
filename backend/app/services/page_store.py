"""Published pages and their audit, in SQLite.

Durable: live pages, their expiry, a HASH of each unpublish token (never the token), and
append-only records of what was published, unpublished or refused. Page text is removed as soon
as a page ends (taken down or expired); only a tombstone with hashes remains, and its slug, so a
slug is never reused. Records hold a random page reference and the config hash, never page text,
a slug of a refused attempt, a token, or a visitor's address.

The seeded example page has no token and no expiry: nothing public can unpublish it.
"""

import hashlib
import hmac
import sqlite3
from datetime import UTC, datetime, timedelta
from typing import Literal

from pydantic import BaseModel, ConfigDict

from app.schemas.storefront import StorefrontConfig
from app.services.approvals import AuditLog, AuditRecord
from app.services.clock import Clock
from app.services.database import Database

PAGE_LIFETIME = timedelta(days=7)
EXAMPLE_SLUG = "example-pune-cakes"
EXAMPLE_REF = "example"

PageStatus = Literal["live", "unpublished", "expired"]
PageEventName = Literal["published", "unpublished", "unpublish_refused", "expired", "seeded"]

_NO_TOKEN = "0" * 64  # compared against when a page has no token, so timing stays the same


class SlugTaken(Exception):
    """The slug is already in use (live or ended). Slugs are never reused."""


class PageEvent(BaseModel):
    model_config = ConfigDict(frozen=True)

    seq: int
    at: datetime
    event: PageEventName
    page_ref: str | None
    config_hash: str | None


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def _epoch(moment: datetime) -> int:
    return int(moment.timestamp())


def _moment(epoch: int) -> datetime:
    return datetime.fromtimestamp(epoch, tz=UTC)


_APPEND_ONLY = """
CREATE TRIGGER IF NOT EXISTS {table}_no_update BEFORE UPDATE ON {table}
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
CREATE TRIGGER IF NOT EXISTS {table}_no_delete BEFORE DELETE ON {table}
BEGIN SELECT RAISE(ABORT, 'append-only'); END;
"""

_PAGE_SCHEMA = """
CREATE TABLE IF NOT EXISTS pages (
    slug TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    config_json TEXT,
    config_hash TEXT NOT NULL,
    token_hash TEXT,
    protected INTEGER NOT NULL DEFAULT 0,
    status TEXT NOT NULL,
    created_at INTEGER NOT NULL,
    expires_at INTEGER,
    ended_at INTEGER
);
CREATE TABLE IF NOT EXISTS page_events (
    seq INTEGER PRIMARY KEY AUTOINCREMENT,
    at INTEGER NOT NULL,
    event TEXT NOT NULL,
    page_ref TEXT,
    config_hash TEXT
);
""" + _APPEND_ONLY.format(table="page_events")


class PageStore:
    def __init__(self, db: Database, clock: Clock) -> None:
        self._db = db
        self._clock = clock
        db.script(_PAGE_SCHEMA)

    # -- reads --

    def get_live(self, slug: str) -> StorefrontConfig | None:
        rows = self._db.query(
            "SELECT config_json FROM pages WHERE slug = ? AND status = 'live' "
            "AND (expires_at IS NULL OR expires_at > ?)",
            (slug, _epoch(self._clock.now())),
        )
        if not rows or rows[0][0] is None:
            return None
        return StorefrontConfig.model_validate_json(rows[0][0])

    def status_of(self, slug: str) -> PageStatus | None:
        rows = self._db.query("SELECT status, expires_at FROM pages WHERE slug = ?", (slug,))
        if not rows:
            return None
        status, expires_at = rows[0]
        if status == "live" and expires_at is not None and expires_at <= _epoch(self._clock.now()):
            return "expired"
        return str(status)  # type: ignore[return-value]

    def live_count(self) -> int:
        """Pages that count toward the cap: live, not expired, and not the seeded example."""
        rows = self._db.query(
            "SELECT COUNT(*) FROM pages WHERE status = 'live' AND protected = 0 AND expires_at > ?",
            (_epoch(self._clock.now()),),
        )
        return int(rows[0][0])

    def events(self) -> list[PageEvent]:
        rows = self._db.query(
            "SELECT seq, at, event, page_ref, config_hash FROM page_events ORDER BY seq"
        )
        return [PageEvent(seq=r[0], at=_moment(r[1]), event=r[2], page_ref=r[3], config_hash=r[4])
                for r in rows]  # fmt: skip

    # -- commands --

    def add_live(
        self,
        *,
        slug: str,
        config: StorefrontConfig,
        config_hash: str,
        run_id: str,
        token_hash: str,
        expires_at: datetime,
    ) -> None:
        now = self._clock.now()
        try:
            with self._db.transaction():
                self._db.execute(
                    "INSERT INTO pages (slug, run_id, config_json, config_hash, token_hash, "
                    "protected, status, created_at, expires_at) "
                    "VALUES (?, ?, ?, ?, ?, 0, 'live', ?, ?)",
                    (slug, run_id, config.model_dump_json(), config_hash, token_hash,
                     _epoch(now), _epoch(expires_at)),
                )  # fmt: skip
                self._event("published", run_id, config_hash)
        except sqlite3.IntegrityError as exc:
            raise SlugTaken("slug is already in use") from exc

    def seed_example(self, config: StorefrontConfig, config_hash: str) -> bool:
        """Create the example page if it is missing. It has no token and never expires."""
        with self._db.transaction():
            changed = self._db.execute(
                "INSERT OR IGNORE INTO pages (slug, run_id, config_json, config_hash, token_hash, "
                "protected, status, created_at, expires_at) "
                "VALUES (?, ?, ?, ?, NULL, 1, 'live', ?, NULL)",
                (EXAMPLE_SLUG, EXAMPLE_REF, config.model_dump_json(), config_hash,
                 _epoch(self._clock.now())),
            )  # fmt: skip
            if changed:
                self._event("seeded", EXAMPLE_REF, config_hash)
        return bool(changed)

    def unpublish(self, slug: str, presented_hash: str) -> str | None:
        """Take a page down if the token hash matches. Returns its page reference, or None.

        Every failure (unknown page, ended page, the example page, wrong token) is the same
        outcome, so nothing can be learned by probing.
        """
        with self._db.transaction():
            rows = self._db.query(
                "SELECT run_id, token_hash, protected, status, expires_at, config_hash "
                "FROM pages WHERE slug = ?",
                (slug,),
            )
            run_id: str | None = None
            if rows:
                ref, stored, protected, status, expires_at, config_hash = rows[0]
                live = status == "live" and (
                    expires_at is None or expires_at > _epoch(self._clock.now())
                )
                matches = hmac.compare_digest(stored or _NO_TOKEN, presented_hash)
                if live and not protected and stored is not None and matches:
                    run_id = str(ref)
            else:
                hmac.compare_digest(_NO_TOKEN, presented_hash)
            if run_id is None:
                self._event("unpublish_refused", None, None)
                return None
            self._end(slug, "unpublished")
            self._event("unpublished", run_id, str(config_hash))
            return run_id

    def purge_expired(self) -> int:
        """Clear the text of pages whose time is up, and record it. The example never expires."""
        now = _epoch(self._clock.now())
        with self._db.transaction():
            rows = self._db.query(
                "SELECT slug, run_id, config_hash FROM pages "
                "WHERE status = 'live' AND expires_at IS NOT NULL AND expires_at <= ?",
                (now,),
            )
            for slug, run_id, config_hash in rows:
                self._end(slug, "expired")
                self._event("expired", run_id, config_hash)
        return len(rows)

    # -- internals --

    def _end(self, slug: str, status: str) -> None:
        self._db.execute(
            "UPDATE pages SET status = ?, config_json = NULL, token_hash = NULL, ended_at = ? "
            "WHERE slug = ?",
            (status, _epoch(self._clock.now()), slug),
        )

    def _event(self, event: PageEventName, page_ref: str | None, config_hash: str | None) -> None:
        self._db.execute(
            "INSERT INTO page_events (at, event, page_ref, config_hash) VALUES (?, ?, ?, ?)",
            (_epoch(self._clock.now()), event, page_ref, config_hash),
        )


_AUDIT_SCHEMA = """
CREATE TABLE IF NOT EXISTS audit (
    seq INTEGER PRIMARY KEY,
    actor TEXT NOT NULL,
    record TEXT NOT NULL
);
""" + _APPEND_ONLY.format(table="audit")


class SqliteAuditLog(AuditLog):
    """The approval audit log, kept in SQLite. Same rules as the in-memory one: append-only,
    numbered 1, 2, 3, and hashes only. Numbering continues after a restart."""

    def __init__(self, db: Database) -> None:
        super().__init__()
        self._db = db
        db.script(_AUDIT_SCHEMA)

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        rows = self._db.query("SELECT record FROM audit ORDER BY seq")
        return tuple(AuditRecord.model_validate_json(r[0]) for r in rows)

    def next_seq(self) -> int:
        return int(self._db.query("SELECT COALESCE(MAX(seq), 0) + 1 FROM audit")[0][0])

    def append(self, record: AuditRecord) -> None:
        if record.seq != self.next_seq():
            raise ValueError(f"audit seq must be {self.next_seq()}, got {record.seq}")
        self._db.execute(
            "INSERT INTO audit (seq, actor, record) VALUES (?, ?, ?)",
            (record.seq, record.actor, record.model_dump_json()),
        )
