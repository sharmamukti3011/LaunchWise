"""The deployer for starter pages: "deploying" means storing the approved page, live.

It is only ever called by the DeployGuard, after the approval service has verified a granted,
unexpired, unused launch approval for this exact payload. It also checks that what it is about to
store is the config the payload names, so a payload and a page cannot drift apart.
"""

from dataclasses import dataclass

from pydantic import Field

from app.engine.approval_payload import hash_model
from app.schemas.storefront import StorefrontConfig
from app.services.approvals import LaunchPayload
from app.services.clock import Clock
from app.services.deploy_guard import DeployError
from app.services.page_store import PAGE_LIFETIME, PageStore


class PublishPayload(LaunchPayload):
    """What the owner approves: this exact page at this address."""

    slug: str = Field(pattern=r"^[a-z0-9][a-z0-9-]{0,79}$")
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


@dataclass(frozen=True)
class _Pending:
    config: StorefrontConfig
    token_hash: str


class PagePublisher:
    def __init__(self, store: PageStore, clock: Clock) -> None:
        self._store = store
        self._clock = clock
        self._pending: dict[str, _Pending] = {}

    def prepare(self, run_id: str, config: StorefrontConfig, token_hash: str) -> None:
        self._pending[run_id] = _Pending(config, token_hash)

    def deploy(self, run_id: str, payload: LaunchPayload) -> None:
        pending = self._pending.pop(run_id, None)
        if pending is None or not isinstance(payload, PublishPayload):
            raise DeployError("nothing prepared for this run")
        if hash_model(pending.config) != payload.config_hash:
            raise DeployError("the page differs from the approved one")
        self._store.add_live(
            slug=payload.slug,
            config=pending.config,
            config_hash=payload.config_hash,
            run_id=run_id,
            token_hash=pending.token_hash,
            expires_at=self._clock.now() + PAGE_LIFETIME,
        )
