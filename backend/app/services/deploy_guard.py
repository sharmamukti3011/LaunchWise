"""Deploy guard: a thin wrapper that calls the deployer only after the approval transition.

It has no approval logic of its own. `ApprovalService.transition(DEPLOYING, payload)` checks the
state, the approval (granted, unexpired, unused), the payload hash and the strategy chain, and
spends the approval. If that raises, nothing is deployed.
"""

from typing import Protocol

from app.engine.approval_rules import State
from app.services.approvals import ApprovalService, LaunchPayload


class DeployError(Exception):
    """What a deployer raises for an expected failure (build, upload, promote)."""


class DeployFailed(Exception):
    """The deployer failed after the approval was spent. `__cause__` is the original error."""


class Deployer(Protocol):
    def deploy(self, run_id: str, payload: LaunchPayload) -> None:
        """Render, promote and keep the previous version. Raise on failure."""
        ...


class DeployGuard:
    def __init__(self, approvals: ApprovalService, deployer: Deployer) -> None:
        self._approvals = approvals
        self._deployer = deployer

    def deploy(self, run_id: str, payload: LaunchPayload, actor: str) -> State:
        # Raises (and audits the refusal) unless a matching approval exists; spends it on success.
        self._approvals.transition(run_id, State.DEPLOYING, actor, payload)
        try:
            self._deployer.deploy(run_id, payload)
        except Exception as exc:
            # External boundary: any escape would leave the run stuck in DEPLOYING with a spent
            # approval. Record FAILED (class name only, messages may hold paths or secrets).
            self._approvals.transition(run_id, State.FAILED, actor, detail=type(exc).__name__)
            raise DeployFailed("deployment failed") from exc
        return self._approvals.transition(run_id, State.LIVE, actor)
