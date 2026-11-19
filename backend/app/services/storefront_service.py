"""Starter pages: preview, approve and publish, unpublish.

A preview creates a draft and goes through the approval service: a run is started and an approval
for the EXACT config is requested. Nothing is public until the owner clicks "Approve and publish".
That one explicit action grants both approvals (strategy, then launch) server-side, each audited,
and then calls the deploy guard, which refuses unless a matching launch approval exists. The audit
log holds hashes only. Logs hold outcomes only: never the page text, the contact address, an
unpublish token, a slug, or the visitor's address.
"""

import hmac
import logging
import re
import secrets
import threading
import unicodedata
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from uuid import uuid4

from pydantic import BaseModel, ConfigDict

from app.engine.approval_payload import hash_model
from app.engine.approval_rules import State
from app.schemas.starter import StarterPageRequest, to_config
from app.schemas.storefront import StorefrontConfig
from app.services.approvals import (
    APPROVE_LAUNCH,
    APPROVE_STRATEGY,
    ApprovalError,
    ApprovalService,
)
from app.services.clock import Clock
from app.services.database import Database
from app.services.deploy_guard import DeployFailed, DeployGuard
from app.services.page_store import PAGE_LIFETIME, PageStore, hash_token
from app.services.rate_limit import RateLimited, RateLimiter
from app.services.storefront_publisher import PagePublisher, PublishPayload
from app.services.storefront_render import render_page

# Outcomes only: never the page text, the contact address, or the visitor's address.
logger = logging.getLogger("launchwise.storefront")

DRAFT_TTL = timedelta(minutes=30)
MAX_DRAFTS = 500
ACTOR = "visitor"  # a role, never an address: the audit log carries no personal data
OWNER = "owner"  # who clicks "Approve and publish": also a role
MAX_LIVE_PAGES = 50
PUBLISHES_PER_HOUR = 3
UNPUBLISH_ATTEMPTS_PER_HOUR = 10
MAX_SLUG_WORDS_LENGTH = 30
OVERALL_KEY = "all-visitors"


class PreviewResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    draft_id: str
    slug: str
    public_path: str
    config_hash: str
    expires_in_minutes: int
    preview_html: str


class PublishResult(BaseModel):
    model_config = ConfigDict(frozen=True)

    slug: str
    public_path: str
    # Shown once. Only its hash is stored, so it cannot be shown again.
    unpublish_token: str
    expires_in_days: int


class StorefrontError(Exception):
    """Base for the refusals below. None of them carries anything the visitor typed."""


class DraftNotFound(StorefrontError): ...


class DraftChanged(StorefrontError): ...


class PublishCapReached(StorefrontError): ...


class PublishFailed(StorefrontError): ...


class UnpublishRefused(StorefrontError): ...


@dataclass(frozen=True)
class _Draft:
    config: StorefrontConfig
    config_hash: str
    slug: str
    approval_id: str
    created_at: datetime


def make_slug(brand: str, suffix: str) -> str:
    """A readable, URL-safe slug: the name in plain ASCII, then a random part so it is unique."""
    folded = unicodedata.normalize("NFKD", brand)
    ascii_text = folded.encode("ascii", "ignore").decode("ascii").lower()
    words = re.sub(r"[^a-z0-9]+", "-", ascii_text).strip("-")[:MAX_SLUG_WORDS_LENGTH].strip("-")
    return f"{words or 'page'}-{suffix}"


class StorefrontService:
    def __init__(
        self,
        approvals: ApprovalService,
        clock: Clock,
        per_client: RateLimiter,
        overall: RateLimiter | None = None,
        *,
        id_factory: Callable[[], str] | None = None,
        suffix_factory: Callable[[], str] | None = None,
        max_drafts: int = MAX_DRAFTS,
        pages: PageStore | None = None,
        publish_limiter: RateLimiter | None = None,
        unpublish_limiter: RateLimiter | None = None,
        max_live_pages: int = MAX_LIVE_PAGES,
    ) -> None:
        self._approvals = approvals
        self._clock = clock
        self._per_client = per_client
        self._overall = overall
        self._new_id = id_factory or (lambda: uuid4().hex)
        self._new_suffix = suffix_factory or (lambda: secrets.token_hex(3))
        self._max_drafts = max_drafts
        self._drafts: OrderedDict[str, _Draft] = OrderedDict()
        self._lock = threading.RLock()
        self._publish_lock = threading.Lock()
        # `is None`, not `or`: an empty RateLimiter has len 0 and so counts as false.
        self._pages = pages if pages is not None else PageStore(Database(":memory:"), clock)
        self._publish_limiter = (
            publish_limiter
            if publish_limiter is not None
            else RateLimiter(limit=PUBLISHES_PER_HOUR, window=timedelta(hours=1), clock=clock)
        )
        self._unpublish_limiter = (
            unpublish_limiter
            if unpublish_limiter is not None
            else RateLimiter(
                limit=UNPUBLISH_ATTEMPTS_PER_HOUR, window=timedelta(hours=1), clock=clock
            )
        )
        self._max_live_pages = max_live_pages
        self._publisher = PagePublisher(self._pages, clock)
        self._guard = DeployGuard(approvals, self._publisher)

    # -- reads --

    def has_draft(self, draft_id: str) -> bool:
        with self._lock:
            self._prune()
            return draft_id in self._drafts

    def approval_id_of(self, draft_id: str) -> str:
        return self._drafts[draft_id].approval_id

    def page_html(self, slug: str) -> str | None:
        """The live page for this slug, or None when it is unknown, expired or taken down."""
        config = self._pages.get_live(slug)
        return render_page(config) if config is not None else None

    # -- commands --

    def preview(self, request: StarterPageRequest, client_key: str) -> PreviewResult:
        try:
            # Per visitor first, then overall: a visitor already blocked must not use up the shared
            # cap that everyone else depends on.
            self._per_client.check(client_key)
            if self._overall is not None:
                self._overall.check(OVERALL_KEY)
        except RateLimited:
            logger.info("storefront outcome=rate_limited")
            raise
        config = to_config(request)
        digest = hash_model(config)
        draft_id = self._new_id()
        self._approvals.start_run(draft_id, ACTOR)
        self._approvals.transition(draft_id, State.STRATEGY_PROPOSED, ACTOR)
        approval = self._approvals.request_approval(draft_id, APPROVE_STRATEGY, config, ACTOR)
        slug = make_slug(config.brand, self._new_suffix())
        with self._lock:
            self._prune()
        self._drafts[draft_id] = _Draft(
            config, digest, slug, approval.approval_id, self._clock.now()
        )
        while len(self._drafts) > self._max_drafts:
            self._drafts.popitem(last=False)  # the oldest draft goes first
        logger.info("storefront outcome=preview_created")
        return PreviewResult(
            draft_id=draft_id,
            slug=slug,
            public_path=f"/s/{slug}",
            config_hash=digest,
            expires_in_minutes=int(DRAFT_TTL.total_seconds() // 60),
            preview_html=render_page(config),
        )

    def publish(self, draft_id: str, config_hash: str, client_key: str) -> PublishResult:
        """ "Approve and publish". Only an explicit call gets here; nothing else grants approval."""
        with self._publish_lock:
            draft = self._draft_for(draft_id, config_hash)
            try:
                self._publish_limiter.check(client_key)
            except RateLimited:
                logger.info("storefront outcome=publish_rate_limited")
                raise
            self._pages.purge_expired()
            if self._pages.live_count() >= self._max_live_pages:
                logger.info("storefront outcome=publish_cap_reached")
                raise PublishCapReached("too many live pages")
            with self._lock:
                self._drafts.pop(draft_id, None)  # one preview can be published only once
            token = secrets.token_urlsafe(32)
            payload = PublishPayload(
                slug=draft.slug,
                config_hash=draft.config_hash,
                strategy_payload_hash=draft.config_hash,
            )
            try:
                self._approve(draft_id, draft, payload)
                self._publisher.prepare(draft_id, draft.config, hash_token(token))
                self._guard.deploy(draft_id, payload, OWNER)
            except (ApprovalError, DeployFailed) as exc:
                logger.info("storefront outcome=publish_failed")
                raise PublishFailed("the page could not be published") from exc
        logger.info("storefront outcome=published")
        return PublishResult(
            slug=draft.slug,
            public_path=f"/s/{draft.slug}",
            unpublish_token=token,
            expires_in_days=PAGE_LIFETIME.days,
        )

    def unpublish(self, slug: str, token: str, client_key: str) -> None:
        try:
            self._unpublish_limiter.check(client_key)
        except RateLimited:
            logger.info("storefront outcome=unpublish_rate_limited")
            raise
        if self._pages.unpublish(slug, hash_token(token)) is None:
            logger.info("storefront outcome=unpublish_refused")
            raise UnpublishRefused("that unpublish link is not valid")
        logger.info("storefront outcome=unpublished")

    # -- internals --

    def _draft_for(self, draft_id: str, config_hash: str) -> _Draft:
        with self._lock:
            self._prune()
            draft = self._drafts.get(draft_id)
        if draft is None:
            raise DraftNotFound("no such preview")
        if not hmac.compare_digest(draft.config_hash, config_hash):
            raise DraftChanged("the page changed since it was previewed")
        return draft

    def _approve(self, run_id: str, draft: _Draft, payload: PublishPayload) -> None:
        """Both approvals, granted by the one explicit click, each recorded in the audit log."""
        self._approvals.decide(draft.approval_id, draft.config, True, OWNER)
        self._approvals.transition(run_id, State.STRATEGY_APPROVED, OWNER, draft.config)
        launch = self._approvals.request_approval(run_id, APPROVE_LAUNCH, payload, OWNER)
        self._approvals.decide(launch.approval_id, payload, True, OWNER)
        self._approvals.transition(run_id, State.LAUNCH_APPROVED, OWNER, payload)

    def _prune(self) -> None:
        cutoff = self._clock.now() - DRAFT_TTL
        for draft_id in [d for d, draft in self._drafts.items() if draft.created_at <= cutoff]:
            del self._drafts[draft_id]
