"""Live pages live in SQLite: expiry, a token hash (never the token), and audit that outlives a
restart. The raw token and the page text must never be stored once a page has ended."""

import sqlite3
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from app.engine.approval_payload import hash_model
from app.schemas.storefront import StorefrontConfig
from app.services.approvals import ApprovalService
from app.services.database import Database
from app.services.page_store import (
    EXAMPLE_SLUG,
    PAGE_LIFETIME,
    PageStore,
    SlugTaken,
    SqliteAuditLog,
    hash_token,
)
from tests.fakes import FakeClock

TOKEN = "t0ken-" + "x" * 30
SENTINEL = "ZQSENTINEL"


def config(brand: str = "Aarti's") -> StorefrontConfig:
    return StorefrontConfig.model_validate(
        {"brand": brand, "products": [{"name": "Cake", "price": "500"}]}
    )


def make(tmp_path: Path, clock: FakeClock | None = None) -> tuple[PageStore, FakeClock, Path]:
    clock = clock or FakeClock()
    path = tmp_path / "launchwise.db"
    return PageStore(Database(str(path)), clock), clock, path


def add(store: PageStore, clock: FakeClock, slug: str = "aarti-a1", brand: str = "Aarti's") -> str:
    cfg = config(brand)
    store.add_live(
        slug=slug,
        config=cfg,
        config_hash=hash_model(cfg),
        run_id="run-0001",
        token_hash=hash_token(TOKEN),
        expires_at=clock.now() + PAGE_LIFETIME,
    )
    return slug


def test_pages_last_seven_days() -> None:
    assert timedelta(days=7) == PAGE_LIFETIME


def test_a_live_page_is_served_until_it_expires(tmp_path: Path) -> None:
    store, clock, _ = make(tmp_path)
    add(store, clock)
    assert store.get_live("aarti-a1") == config()
    clock.advance(PAGE_LIFETIME - timedelta(seconds=1))
    assert store.get_live("aarti-a1") is not None
    clock.advance(timedelta(seconds=1))
    assert store.get_live("aarti-a1") is None
    assert store.status_of("aarti-a1") == "expired"


def test_an_unknown_slug_is_simply_absent(tmp_path: Path) -> None:
    store, _, _ = make(tmp_path)
    assert store.get_live("nope") is None and store.status_of("nope") is None


def test_a_slug_can_never_be_reused(tmp_path: Path) -> None:
    store, clock, _ = make(tmp_path)
    add(store, clock)
    with pytest.raises(SlugTaken):
        add(store, clock)
    store.unpublish("aarti-a1", hash_token(TOKEN))
    with pytest.raises(SlugTaken):
        add(store, clock)


def test_pages_survive_a_restart_and_so_do_their_expiry(tmp_path: Path) -> None:
    store, clock, path = make(tmp_path)
    add(store, clock)
    reopened = PageStore(Database(str(path)), clock)
    assert reopened.get_live("aarti-a1") == config()
    clock.advance(PAGE_LIFETIME)
    assert reopened.get_live("aarti-a1") is None


def test_only_a_hash_of_the_token_is_stored_never_the_token(tmp_path: Path) -> None:
    store, clock, path = make(tmp_path)
    add(store, clock)
    raw = path.read_bytes()
    assert TOKEN.encode() not in raw
    assert hash_token(TOKEN) != TOKEN and len(hash_token(TOKEN)) == 64


# ---- unpublish --------------------------------------------------------------------------------


def test_the_right_token_takes_a_page_down_and_clears_its_text(tmp_path: Path) -> None:
    store, clock, path = make(tmp_path)
    add(store, clock, brand=f"{SENTINEL} Cakes")
    assert store.unpublish("aarti-a1", hash_token(TOKEN)) == "run-0001"
    assert store.get_live("aarti-a1") is None and store.status_of("aarti-a1") == "unpublished"
    assert SENTINEL.encode() not in path.read_bytes()  # the page text is gone, not just hidden


def test_a_wrong_token_changes_nothing(tmp_path: Path) -> None:
    store, clock, _ = make(tmp_path)
    add(store, clock)
    assert store.unpublish("aarti-a1", hash_token("wrong")) is None
    assert store.get_live("aarti-a1") is not None


def test_unpublishing_twice_or_an_unknown_page_is_refused(tmp_path: Path) -> None:
    store, clock, _ = make(tmp_path)
    add(store, clock)
    assert store.unpublish("aarti-a1", hash_token(TOKEN)) is not None
    assert store.unpublish("aarti-a1", hash_token(TOKEN)) is None
    assert store.unpublish("ghost", hash_token(TOKEN)) is None


# ---- expiry housekeeping and the cap ----------------------------------------------------------


def test_the_live_count_ignores_expired_and_unpublished_pages(tmp_path: Path) -> None:
    store, clock, _ = make(tmp_path)
    add(store, clock, "a-1")
    add(store, clock, "b-1")
    assert store.live_count() == 2
    store.unpublish("a-1", hash_token(TOKEN))
    assert store.live_count() == 1
    clock.advance(PAGE_LIFETIME)
    assert store.live_count() == 0


def test_purging_expired_pages_clears_their_text(tmp_path: Path) -> None:
    store, clock, path = make(tmp_path)
    add(store, clock, brand=f"{SENTINEL} Cakes")
    add(store, clock, "b-1")
    clock.advance(PAGE_LIFETIME)
    assert store.purge_expired() == 2
    assert SENTINEL.encode() not in path.read_bytes()
    assert store.purge_expired() == 0


# ---- the example page -------------------------------------------------------------------------


def test_the_example_page_is_seeded_once_and_never_expires(tmp_path: Path) -> None:
    store, clock, _ = make(tmp_path)
    cfg = config("Example")
    assert store.seed_example(cfg, hash_model(cfg)) is True
    assert store.seed_example(cfg, hash_model(cfg)) is False  # already there
    clock.advance(timedelta(days=3650))
    assert store.get_live(EXAMPLE_SLUG) == cfg
    assert store.purge_expired() == 0


def test_the_example_page_cannot_be_unpublished_with_any_token(tmp_path: Path) -> None:
    store, _, _ = make(tmp_path)
    cfg = config("Example")
    store.seed_example(cfg, hash_model(cfg))
    for token in (TOKEN, "", "None", "null", hash_token("")):
        assert store.unpublish(EXAMPLE_SLUG, hash_token(token)) is None
        assert store.unpublish(EXAMPLE_SLUG, token) is None
    assert store.get_live(EXAMPLE_SLUG) == cfg


def test_the_example_page_does_not_count_toward_the_cap(tmp_path: Path) -> None:
    store, _, _ = make(tmp_path)
    cfg = config("Example")
    store.seed_example(cfg, hash_model(cfg))
    assert store.live_count() == 0


# ---- page events (publish / unpublish audit) --------------------------------------------------


def test_publishing_and_unpublishing_are_recorded_with_hashes_only(tmp_path: Path) -> None:
    store, clock, path = make(tmp_path)
    add(store, clock, brand=f"{SENTINEL} Cakes")
    store.unpublish("aarti-a1", hash_token(TOKEN))
    events = store.events()
    assert [e.event for e in events] == ["published", "unpublished"]
    assert all(e.page_ref == "run-0001" for e in events)
    assert events[0].config_hash == hash_model(config(f"{SENTINEL} Cakes"))
    dump = repr([e.model_dump() for e in events])
    assert SENTINEL not in dump and "aarti-a1" not in dump and TOKEN not in dump


def test_events_outlive_the_pages_text_and_a_restart(tmp_path: Path) -> None:
    store, clock, path = make(tmp_path)
    add(store, clock)
    clock.advance(PAGE_LIFETIME)
    store.purge_expired()
    reopened = PageStore(Database(str(path)), clock)
    assert [e.event for e in reopened.events()] == ["published", "expired"]


def test_events_can_only_be_added_never_edited_or_removed(tmp_path: Path) -> None:
    store, clock, path = make(tmp_path)
    add(store, clock)
    with sqlite3.connect(path) as raw:
        triggers = raw.execute("select name from sqlite_master where type = 'trigger'").fetchall()
    assert len(triggers) >= 2  # one each for UPDATE and DELETE on the event tables


# ---- the approval audit log, persisted --------------------------------------------------------


def approvals(tmp_path: Path, clock: FakeClock) -> tuple[ApprovalService, Path]:
    path = tmp_path / "audit.db"
    return ApprovalService(clock, audit=SqliteAuditLog(Database(str(path)))), path


def test_the_approval_audit_log_is_kept_across_a_restart_and_its_numbering_continues(
    tmp_path: Path,
) -> None:
    clock = FakeClock()
    first, path = approvals(tmp_path, clock)
    first.start_run("r1", "visitor")
    assert [r.seq for r in first.audit.records] == [1]
    second = ApprovalService(clock, audit=SqliteAuditLog(Database(str(path))))
    assert [r.event for r in second.audit.records] == ["run_started"]
    second.start_run("r2", "visitor")
    assert [r.seq for r in second.audit.records] == [1, 2]


def test_the_audit_log_rejects_out_of_order_records(tmp_path: Path) -> None:
    service, _ = approvals(tmp_path, FakeClock())
    service.start_run("r1", "visitor")
    last = service.audit.records[-1]
    with pytest.raises(ValueError):
        service.audit.append(last)


def test_audit_rows_cannot_be_edited_or_deleted(tmp_path: Path) -> None:
    service, path = approvals(tmp_path, FakeClock())
    service.start_run("r1", "visitor")
    with sqlite3.connect(path) as raw:
        for sql in ("update audit set actor = 'x'", "delete from audit"):
            with pytest.raises(sqlite3.DatabaseError):
                raw.execute(sql)


def test_the_database_is_created_with_its_folder(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "dir" / "x.db"
    Database(str(target))
    assert target.exists()


def test_a_memory_database_works_for_tests(tmp_path: Path) -> None:
    clock = FakeClock()
    store = PageStore(Database(":memory:"), clock)
    add(store, clock)
    assert store.live_count() == 1


def _unused(*_: Any) -> None: ...
