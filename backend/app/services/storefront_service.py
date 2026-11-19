"""Starter-page preview: build the page from the owner's text and request approval for it.

Nothing is public here. A preview creates a draft and goes through the existing approval service:
a run is started and an approval for the EXACT config is requested, so the audit log records the
request. Publishing (a later step) must present the same config hash and be granted before the
deploy guard will act. The audit log holds hashes only. Logs hold outcomes only: never the page
text, the contact address, or the visitor's address.
"""

import logging
import re
import secrets
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
from app.services.approvals import APPROVE_STRATEGY, ApprovalService
from app.services.clock import Clock
from app.services.rate_limit import RateLimited, RateLimiter
from app.services.storefront_render import render_page

# Outcomes only: never the page text, the contact address, or the visitor's address.
logger = logging.getLogger("launchwise.storefront")

DRAFT_TTL = timedelta(minutes=30)
MAX_DRAFTS = 500
ACTOR = "visitor"  # a role, never an address: the audit log carries no personal data
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
    ) -> None:
        self._approvals = approvals
        self._clock = clock
        self._per_client = per_client
        self._overall = overall
        self._new_id = id_factory or (lambda: uuid4().hex)
        self._new_suffix = suffix_factory or (lambda: secrets.token_hex(3))
        self._max_drafts = max_drafts
        self._drafts: OrderedDict[str, _Draft] = OrderedDict()

    # -- reads --

    def has_draft(self, draft_id: str) -> bool:
        self._prune()
        return draft_id in self._drafts

    def approval_id_of(self, draft_id: str) -> str:
        return self._drafts[draft_id].approval_id

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

    # -- internals --

    def _prune(self) -> None:
        cutoff = self._clock.now() - DRAFT_TTL
        for draft_id in [d for d, draft in self._drafts.items() if draft.created_at <= cutoff]:
            del self._drafts[draft_id]
