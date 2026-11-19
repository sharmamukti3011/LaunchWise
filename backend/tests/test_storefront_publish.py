"""Approve and publish: both approvals are granted by one explicit click, the deploy guard refuses
without a matching approval, and the page is stored durably with a token hash and an audit trail."""

import logging
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest

from app.engine.approval_payload import hash_model
from app.engine.approval_rules import State
from app.schemas.starter import StarterPageRequest, to_config
from app.services.approvals import (
    APPROVE_LAUNCH,
    APPROVE_STRATEGY,
    ApprovalError,
    ApprovalService,
)
from app.services.database import Database
from app.services.deploy_guard import DeployGuard
from app.services.page_store import PAGE_LIFETIME, PageStore, SqliteAuditLog, hash_token
from app.services.rate_limit import RateLimited, RateLimiter
from app.services.storefront_publisher import PagePublisher, PublishPayload
from app.services.storefront_service import (
    DRAFT_TTL,
    DraftChanged,
    DraftNotFound,
    PublishCapReached,
    PublishFailed,
    StorefrontService,
    UnpublishRefused,
)
from tests.fakes import FakeClock, FakeDeployer

SENTINEL = "ZQSENTINEL"
CLIENT = "198.51.100.66"


def request(**overrides: Any) -> StarterPageRequest:
    data: dict[str, Any] = {
        "business_name": "Aarti's Home Bakery",
        "description": "Fresh cakes, made to order.",
        "contact_email": "aarti@example.com",
        "offer_title": "Custom celebration cakes",
        "offer_price": "1200",
        "food_business": True,
    }
    data.update(overrides)
    return StarterPageRequest.model_validate(data)


class World:
    def __init__(
        self,
        tmp_path: Path,
        *,
        publish_limit: int = 100,
        max_live: int = 50,
        fixed_suffix: bool = False,
    ) -> None:
        self.clock = FakeClock()
        self.db = Database(str(tmp_path / "world.db"))
        self.approvals = ApprovalService(self.clock, ttl=DRAFT_TTL, audit=SqliteAuditLog(self.db))
        self.store = PageStore(self.db, self.clock)
        self.counter = 0

        def suffix() -> str:
            self.counter += 1
            return "a1b2c3" if fixed_suffix else f"s{self.counter:05d}"

        self.service = StorefrontService(
            self.approvals,
            self.clock,
            RateLimiter(limit=1000, window=timedelta(hours=1), clock=self.clock),
            pages=self.store,
            publish_limiter=RateLimiter(
                limit=publish_limit, window=timedelta(hours=1), clock=self.clock
            ),
            unpublish_limiter=RateLimiter(limit=5, window=timedelta(hours=1), clock=self.clock),
            max_live_pages=max_live,
            suffix_factory=suffix,
        )

    def draft(self, **overrides: Any) -> Any:
        return self.service.preview(request(**overrides), CLIENT)

    def publish(self, client: str = CLIENT, **overrides: Any) -> Any:
        preview = self.draft(**overrides)
        return preview, self.service.publish(preview.draft_id, preview.config_hash, client)


# ---- publishing -------------------------------------------------------------------------------


def test_approve_and_publish_puts_the_exact_previewed_page_live(tmp_path: Path) -> None:
    world = World(tmp_path)
    preview, result = world.publish()
    assert result.slug == preview.slug and result.public_path == f"/s/{preview.slug}"
    assert world.service.page_html(result.slug) == preview.preview_html
    assert result.expires_in_days == 7


def test_the_unpublish_token_is_returned_once_and_only_its_hash_is_kept(tmp_path: Path) -> None:
    world = World(tmp_path)
    _, result = world.publish()
    assert len(result.unpublish_token) >= 32
    assert result.unpublish_token.encode() not in (tmp_path / "world.db").read_bytes()
    _, other = world.publish()
    assert other.unpublish_token != result.unpublish_token


def test_publishing_grants_both_approvals_and_audits_every_step(tmp_path: Path) -> None:
    world = World(tmp_path)
    preview, _ = world.publish()
    records = [r for r in world.approvals.audit.records if r.run_id == preview.draft_id]
    assert all(r.outcome == "ok" for r in records)
    requested = [r.action for r in records if r.event == "approval_requested"]
    assert requested == [APPROVE_STRATEGY, APPROVE_LAUNCH]
    decisions = [r for r in records if r.event == "approval_decided"]
    assert [d.detail for d in decisions] == ["granted", "granted"]
    assert {d.actor for d in decisions} == {"owner"}
    moves = [r.to_state for r in records if r.event == "transition"]
    assert moves == [
        State.STRATEGY_PROPOSED,
        State.STRATEGY_APPROVED,
        State.LAUNCH_APPROVED,
        State.DEPLOYING,
        State.LIVE,
    ]
    assert world.approvals.state_of(preview.draft_id) == State.LIVE


def test_publish_and_page_events_are_recorded_by_hash(tmp_path: Path) -> None:
    world = World(tmp_path)
    preview, result = world.publish(business_name=f"{SENTINEL} Cakes")
    [event] = world.store.events()
    assert event.event == "published" and event.page_ref == preview.draft_id
    assert event.config_hash == preview.config_hash
    assert SENTINEL not in repr(event) and result.slug not in repr(event)


def test_a_page_cannot_be_published_for_a_preview_the_owner_did_not_see(tmp_path: Path) -> None:
    world = World(tmp_path)
    preview = world.draft()
    with pytest.raises(DraftChanged):
        world.service.publish(preview.draft_id, "0" * 64, CLIENT)
    assert world.store.live_count() == 0
    assert world.service.page_html(preview.slug) is None


def test_an_unknown_or_expired_draft_cannot_be_published(tmp_path: Path) -> None:
    world = World(tmp_path)
    with pytest.raises(DraftNotFound):
        world.service.publish("nope", "0" * 64, CLIENT)
    preview = world.draft()
    world.clock.advance(DRAFT_TTL)
    with pytest.raises(DraftNotFound):
        world.service.publish(preview.draft_id, preview.config_hash, CLIENT)


def test_one_preview_can_be_published_only_once(tmp_path: Path) -> None:
    world = World(tmp_path)
    preview, _ = world.publish()
    with pytest.raises(DraftNotFound):
        world.service.publish(preview.draft_id, preview.config_hash, CLIENT)
    assert world.store.live_count() == 1


def test_a_failed_publish_leaves_nothing_live_and_is_audited(tmp_path: Path) -> None:
    world = World(tmp_path, fixed_suffix=True)  # both previews get the same slug
    world.publish()
    second = world.draft()
    with pytest.raises(PublishFailed):
        world.service.publish(second.draft_id, second.config_hash, CLIENT)
    assert world.store.live_count() == 1
    assert world.approvals.state_of(second.draft_id) == State.FAILED


# ---- the deploy guard -------------------------------------------------------------------------


def launch_payload(slug: str, config_hash: str, strategy_hash: str) -> PublishPayload:
    return PublishPayload(slug=slug, config_hash=config_hash, strategy_payload_hash=strategy_hash)


def test_the_guard_refuses_to_publish_without_any_approval(tmp_path: Path) -> None:
    world = World(tmp_path)
    publisher = PagePublisher(world.store, world.clock)
    fake = FakeDeployer()
    guard = DeployGuard(world.approvals, fake)
    world.approvals.start_run("r1", "visitor")
    cfg = to_config(request())
    payload = launch_payload("s-1", hash_model(cfg), hash_model(cfg))
    with pytest.raises(Exception, match=r".+") as caught:
        guard.deploy("r1", payload, "owner")
    assert caught.type.__name__ in {"InvalidTransition", "WrongState", "ApprovalMissing"}
    assert fake.calls == [] and publisher is not None
    assert world.store.live_count() == 0


def test_the_guard_refuses_a_payload_that_differs_from_the_approved_one(tmp_path: Path) -> None:
    world = World(tmp_path)
    preview = world.draft()
    run = preview.draft_id
    cfg = to_config(request())
    world.approvals.decide(world.service.approval_id_of(run), cfg, True, "owner")
    world.approvals.transition(run, State.STRATEGY_APPROVED, "owner", cfg)
    approved = launch_payload(preview.slug, preview.config_hash, hash_model(cfg))
    launch = world.approvals.request_approval(run, APPROVE_LAUNCH, approved, "owner")
    world.approvals.decide(launch.approval_id, approved, True, "owner")
    world.approvals.transition(run, State.LAUNCH_APPROVED, "owner", approved)
    forged = launch_payload("another-page-a1", preview.config_hash, hash_model(cfg))
    fake = FakeDeployer()
    with pytest.raises(ApprovalError):
        DeployGuard(world.approvals, fake).deploy(run, forged, "owner")
    assert fake.calls == [] and world.store.live_count() == 0


# ---- limits -----------------------------------------------------------------------------------


def test_at_most_fifty_pages_are_live_and_a_slot_frees_when_one_is_unpublished(
    tmp_path: Path,
) -> None:
    world = World(tmp_path, max_live=2)
    _, first = world.publish()
    world.publish()
    preview = world.draft()
    with pytest.raises(PublishCapReached):
        world.service.publish(preview.draft_id, preview.config_hash, CLIENT)
    assert world.service.has_draft(preview.draft_id)  # the owner may try again later
    world.service.unpublish(first.slug, first.unpublish_token, CLIENT)
    world.service.publish(preview.draft_id, preview.config_hash, CLIENT)
    assert world.store.live_count() == 2


def test_the_default_cap_is_fifty() -> None:
    from app.services.storefront_service import MAX_LIVE_PAGES

    assert MAX_LIVE_PAGES == 50


def test_three_publishes_an_hour_per_client(tmp_path: Path) -> None:
    world = World(tmp_path, publish_limit=3)
    for _ in range(3):
        world.publish()
    preview = world.draft()
    with pytest.raises(RateLimited) as caught:
        world.service.publish(preview.draft_id, preview.config_hash, CLIENT)
    assert caught.value.retry_after >= 1
    world.service.publish(preview.draft_id, preview.config_hash, "203.0.113.9")  # another client
    world.clock.advance(timedelta(hours=1))
    world.publish()


def test_expired_pages_free_their_slot_without_a_manual_cleanup(tmp_path: Path) -> None:
    world = World(tmp_path, max_live=1)
    _, first = world.publish()
    world.clock.advance(PAGE_LIFETIME)
    assert world.service.page_html(first.slug) is None
    world.publish()
    assert world.store.live_count() == 1


# ---- unpublish --------------------------------------------------------------------------------


def test_the_token_takes_the_page_down_and_it_is_audited(tmp_path: Path) -> None:
    world = World(tmp_path)
    preview, result = world.publish()
    world.service.unpublish(result.slug, result.unpublish_token, CLIENT)
    assert world.service.page_html(result.slug) is None
    events = world.store.events()
    assert [e.event for e in events] == ["published", "unpublished"]
    assert events[1].page_ref == preview.draft_id


def test_a_wrong_token_or_an_unknown_page_is_refused_the_same_way_and_audited(
    tmp_path: Path,
) -> None:
    world = World(tmp_path)
    _, result = world.publish()
    with pytest.raises(UnpublishRefused):
        world.service.unpublish(result.slug, "wrong-token", CLIENT)
    with pytest.raises(UnpublishRefused):
        world.service.unpublish("no-such-page", result.unpublish_token, CLIENT)
    assert world.service.page_html(result.slug) is not None
    refused = [e for e in world.store.events() if e.event == "unpublish_refused"]
    assert len(refused) == 2 and all(e.page_ref is None for e in refused)
    assert "wrong-token" not in repr(refused) and "no-such-page" not in repr(refused)


def test_unpublish_attempts_are_rate_limited_per_client(tmp_path: Path) -> None:
    world = World(tmp_path)
    for _ in range(5):
        with pytest.raises(UnpublishRefused):
            world.service.unpublish("x-1", "guess", CLIENT)
    with pytest.raises(RateLimited):
        world.service.unpublish("x-1", "guess", CLIENT)


def test_pages_and_events_survive_a_restart(tmp_path: Path) -> None:
    world = World(tmp_path)
    _, result = world.publish()
    again = PageStore(Database(str(tmp_path / "world.db")), world.clock)
    assert again.get_live(result.slug) is not None
    assert hash_token(result.unpublish_token) != result.unpublish_token
    assert [e.event for e in again.events()] == ["published"]


# ---- logs -------------------------------------------------------------------------------------


def test_outcomes_only_are_logged_never_text_tokens_or_clients(
    tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    world = World(tmp_path)
    _, result = world.publish(business_name=f"{SENTINEL} Cakes", contact_email="zq@example.com")
    world.service.unpublish(result.slug, result.unpublish_token, CLIENT)
    lines = [r.getMessage() for r in caplog.records if r.name == "launchwise.storefront"]
    assert lines == [
        "storefront outcome=preview_created",
        "storefront outcome=published",
        "storefront outcome=unpublished",
    ]
    for private in (SENTINEL, "zq@example.com", result.unpublish_token, result.slug, CLIENT):
        assert private not in caplog.text


def test_the_audit_log_holds_no_page_text_token_or_client(tmp_path: Path) -> None:
    world = World(tmp_path)
    _, result = world.publish(business_name=f"{SENTINEL} Cakes", contact_email="zq@example.com")
    world.service.unpublish(result.slug, result.unpublish_token, CLIENT)
    raw = (tmp_path / "world.db").read_bytes()
    for private in (SENTINEL, "zq@example.com", result.unpublish_token, CLIENT):
        assert private.encode() not in raw
