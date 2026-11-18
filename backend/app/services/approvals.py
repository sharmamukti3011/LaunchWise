"""Approval service: run state, approvals bound to payload hashes, and the audit log.

In memory only, with an injected clock. Two rules shape the API:
- `decide()` only records a decision. `transition()` is the single place run state changes.
- Every caller passes a Pydantic model; the hash is always `hash_model(model)`, never caller-made.
"""

import threading
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from enum import StrEnum
from functools import wraps
from typing import Concatenate, Literal, ParamSpec, TypeVar
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field

from app.engine.approval_payload import hash_model
from app.engine.approval_rules import GATED_ACTIONS, InvalidTransition, State, check_transition
from app.services.clock import Clock, SystemClock

__all__ = ["Clock", "SystemClock"]  # re-exported: they used to live here

DEFAULT_TTL = timedelta(minutes=15)

APPROVE_STRATEGY = "approve_strategy"
APPROVE_LAUNCH = "approve_launch"

# Gated moves from the engine table, plus the move into DEPLOYING. Putting that last edge here
# means nothing can reach DEPLOYING without a matching launch approval, whoever calls transition().
_GATES: dict[tuple[State, State], str] = {
    **GATED_ACTIONS,
    (State.LAUNCH_APPROVED, State.DEPLOYING): APPROVE_LAUNCH,
}
# Moves that use the approval up. The launch approval is only checked when entering
# LAUNCH_APPROVED and is consumed on the way into DEPLOYING, so it is spent exactly once.
_CONSUMING_MOVES = {
    (State.STRATEGY_PROPOSED, State.STRATEGY_APPROVED),
    (State.LAUNCH_APPROVED, State.DEPLOYING),
}
# The state a run must be in when an approval for an action is requested.
_REQUEST_STATE: dict[str, State] = {action: src for (src, _), action in GATED_ACTIONS.items()}


# ---- errors -----------------------------------------------------------------------------------


class ApprovalError(Exception):
    """Base for every approval refusal. The class name is the audit `detail` code."""


class RunExists(ApprovalError): ...


class RunNotFound(ApprovalError): ...


class UnknownAction(ApprovalError): ...


class WrongState(ApprovalError): ...


class InvalidPayload(ApprovalError): ...


class ApprovalMissing(ApprovalError): ...


class ApprovalPending(ApprovalError): ...


class ApprovalNotPending(ApprovalError): ...


class ApprovalDenied(ApprovalError): ...


class ApprovalExpired(ApprovalError): ...


class ApprovalAlreadyUsed(ApprovalError): ...


class PayloadMismatch(ApprovalError): ...


class StrategyMismatch(ApprovalError): ...


class ActionMismatch(ApprovalError): ...


class RunMismatch(ApprovalError): ...


# ---- models -----------------------------------------------------------------------------------


class LaunchPayload(BaseModel):
    """Base for the payload of a launch approval. It carries the approved strategy's hash, so a
    launch approval only works for the exact strategy that was approved."""

    model_config = ConfigDict(frozen=True)

    strategy_payload_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class ApprovalStatus(StrEnum):
    PENDING = "PENDING"
    GRANTED = "GRANTED"
    DENIED = "DENIED"
    CONSUMED = "CONSUMED"
    EXPIRED = "EXPIRED"


class Approval(BaseModel):
    model_config = ConfigDict(frozen=True)

    approval_id: str
    run_id: str
    action: str
    payload_hash: str
    created_at: datetime
    expires_at: datetime
    status: ApprovalStatus = ApprovalStatus.PENDING
    decided_at: datetime | None = None
    decided_by: str | None = None


AuditEvent = Literal[
    "run_started", "approval_requested", "approval_decided", "approval_consumed", "transition"
]


class AuditRecord(BaseModel):
    """One audit line. Holds hashes, never payload content, so it carries no personal data."""

    model_config = ConfigDict(frozen=True)

    seq: int
    at: datetime
    event: AuditEvent
    outcome: Literal["ok", "refused"]
    actor: str
    run_id: str | None = None
    from_state: State | None = None
    to_state: State | None = None
    approval_id: str | None = None
    action: str | None = None
    payload_hash: str | None = None
    detail: str | None = None  # error class name when refused; "granted"/"denied" for decisions


class AuditLog:
    """Append-only: records can be added and read, never edited or removed.

    `records` returns an immutable tuple of frozen records. A persistent log (SQLite later)
    only has to implement `append`, `next_seq` and `records`.
    """

    def __init__(self) -> None:
        self._records: list[AuditRecord] = []

    @property
    def records(self) -> tuple[AuditRecord, ...]:
        return tuple(self._records)

    def next_seq(self) -> int:
        return len(self._records) + 1

    def append(self, record: AuditRecord) -> None:
        if record.seq != self.next_seq():
            raise ValueError(f"audit seq must be {self.next_seq()}, got {record.seq}")
        self._records.append(record)


@dataclass
class _Run:
    state: State = State.DRAFT
    approved_strategy_hash: str | None = None


_P = ParamSpec("_P")
_R = TypeVar("_R")


def _locked(
    method: "Callable[Concatenate[ApprovalService, _P], _R]",
) -> "Callable[Concatenate[ApprovalService, _P], _R]":
    """Run a public command under the service lock.

    Check-then-spend must be atomic: FastAPI runs sync routes in a thread pool, and without
    this two concurrent deploys could both pass the approval check before either consumes it.
    The lock is reentrant so commands may call each other, and it is never held while the
    deployer runs (DeployGuard calls the deployer between two separate transitions).
    """

    @wraps(method)
    def wrapper(self: "ApprovalService", /, *args: _P.args, **kwargs: _P.kwargs) -> _R:
        with self._lock:
            return method(self, *args, **kwargs)

    return wrapper


# ---- service ----------------------------------------------------------------------------------


class ApprovalService:
    def __init__(
        self,
        clock: Clock,
        *,
        ttl: timedelta = DEFAULT_TTL,
        id_factory: Callable[[], str] | None = None,
        audit: AuditLog | None = None,
    ) -> None:
        self._clock = clock
        self._ttl = ttl
        self._new_id = id_factory or (lambda: uuid4().hex)
        self.audit = audit or AuditLog()
        self._runs: dict[str, _Run] = {}
        self._approvals: dict[str, Approval] = {}  # insertion order = creation order
        self._lock = threading.RLock()

    # -- reads --

    def state_of(self, run_id: str) -> State:
        return self._lookup_run(run_id).state

    def approved_strategy_hash(self, run_id: str) -> str | None:
        return self._lookup_run(run_id).approved_strategy_hash

    def get_approval(self, approval_id: str) -> Approval:
        approval = self._approvals.get(approval_id)
        if approval is None:
            raise ApprovalMissing("no such approval")
        return approval

    # -- commands --

    @_locked
    def start_run(self, run_id: str, actor: str) -> State:
        if run_id in self._runs:
            raise self._refuse(RunExists("run already exists"), "run_started", actor, run_id)
        self._runs[run_id] = _Run()
        self._log("run_started", actor, run_id=run_id, to_state=State.DRAFT)
        return State.DRAFT

    @_locked
    def request_approval(
        self, run_id: str, action: str, payload: BaseModel, actor: str
    ) -> Approval:
        event: AuditEvent = "approval_requested"
        run = self._run_or_refuse(run_id, event, actor)
        if action not in _REQUEST_STATE:
            raise self._refuse(UnknownAction("unknown action"), event, actor, run_id, action=action)
        if run.state != _REQUEST_STATE[action]:
            error = WrongState(f"{action} cannot be requested in state {run.state.value}")
            raise self._refuse(error, event, actor, run_id, action=action)
        digest = self._hash_or_refuse(payload, event, actor, run_id, action)
        self._check_launch_payload(run, action, payload, digest, event, actor, run_id)
        now = self._clock.now()
        approval = Approval(
            approval_id=self._new_id(),
            run_id=run_id,
            action=action,
            payload_hash=digest,
            created_at=now,
            expires_at=now + self._ttl,
        )
        self._approvals[approval.approval_id] = approval
        self._log(event, actor, run_id=run_id, approval=approval)
        return approval

    @_locked
    def decide(
        self, approval_id: str, payload: BaseModel, granted: bool, decided_by: str
    ) -> Approval:
        """Record the approver's decision on the exact payload they saw. Never changes run state."""
        event: AuditEvent = "approval_decided"
        error: ApprovalError
        approval = self._approval_or_refuse(approval_id, event, decided_by)
        run_id, action = approval.run_id, approval.action
        digest = self._hash_or_refuse(payload, event, decided_by, run_id, action, approval)
        approval = self._refresh(approval)
        if approval.status == ApprovalStatus.EXPIRED:
            raise self._refuse(
                ApprovalExpired("approval expired"), event, decided_by, run_id, approval, digest
            )
        if approval.status != ApprovalStatus.PENDING:
            error = ApprovalNotPending("approval was already decided or used")
            raise self._refuse(error, event, decided_by, run_id, approval, digest)
        if digest != approval.payload_hash:
            error = PayloadMismatch("payload differs from the one the approval was requested for")
            raise self._refuse(error, event, decided_by, run_id, approval, digest)
        decided = approval.model_copy(
            update={
                "status": ApprovalStatus.GRANTED if granted else ApprovalStatus.DENIED,
                "decided_at": self._clock.now(),
                "decided_by": decided_by,
            }
        )
        self._approvals[approval_id] = decided
        self._log(
            event,
            decided_by,
            run_id=run_id,
            approval=decided,
            detail="granted" if granted else "denied",
        )
        return decided

    @_locked
    def consume(
        self, approval_id: str, run_id: str, action: str, payload: BaseModel, actor: str
    ) -> Approval:
        """Spend a granted approval. It must match run, action and the exact payload."""
        event: AuditEvent = "approval_consumed"
        error: ApprovalError
        approval = self._approval_or_refuse(approval_id, event, actor)
        if approval.run_id != run_id:
            error = RunMismatch("approval belongs to another run")
            raise self._refuse(error, event, actor, run_id, approval)
        if approval.action != action:
            error = ActionMismatch("approval is for a different action")
            raise self._refuse(error, event, actor, run_id, approval)
        digest = self._hash_or_refuse(payload, event, actor, run_id, action, approval)
        approval = self._require_granted(self._refresh(approval), event, actor, digest)
        if digest != approval.payload_hash:
            error = PayloadMismatch("payload differs from the approved one")
            raise self._refuse(error, event, actor, run_id, approval, digest)
        return self._spend(approval, actor)

    @_locked
    def transition(
        self,
        run_id: str,
        to_state: State,
        actor: str,
        payload: BaseModel | None = None,
        *,
        detail: str | None = None,
    ) -> State:
        """The only function that changes run state. Gated moves verify the payload's hash."""
        event: AuditEvent = "transition"
        run = self._run_or_refuse(run_id, event, actor)
        src = run.state
        try:
            check_transition(src, to_state)
        except InvalidTransition as exc:
            raise self._refuse(
                exc, event, actor, run_id, from_state=src, to_state=to_state
            ) from exc

        approval: Approval | None = None
        digest: str | None = None
        action = _GATES.get((src, to_state))
        if action is not None:
            approval, digest = self._verify_gate(run, run_id, src, to_state, action, payload, actor)
            if (src, to_state) in _CONSUMING_MOVES:
                approval = self._spend(approval, actor)
            if to_state == State.STRATEGY_APPROVED:
                run.approved_strategy_hash = digest

        if to_state == State.DRAFT:
            run.approved_strategy_hash = None  # a restarted strategy needs a fresh approval
        run.state = to_state
        self._log(
            event,
            actor,
            run_id=run_id,
            from_state=src,
            to_state=to_state,
            approval=approval,
            detail=detail,
        )
        return to_state

    # -- internals --

    def _lookup_run(self, run_id: str) -> _Run:
        run = self._runs.get(run_id)
        if run is None:
            raise RunNotFound("no such run")
        return run

    def _run_or_refuse(self, run_id: str, event: AuditEvent, actor: str) -> _Run:
        run = self._runs.get(run_id)
        if run is None:
            raise self._refuse(RunNotFound("no such run"), event, actor, run_id)
        return run

    def _approval_or_refuse(self, approval_id: str, event: AuditEvent, actor: str) -> Approval:
        approval = self._approvals.get(approval_id)
        if approval is None:
            error = ApprovalMissing("no such approval")
            raise self._refuse(error, event, actor, approval_id=approval_id)
        return approval

    def _hash_or_refuse(
        self,
        payload: BaseModel,
        event: AuditEvent,
        actor: str,
        run_id: str,
        action: str,
        approval: Approval | None = None,
    ) -> str:
        try:
            return hash_model(payload)
        except (TypeError, ValueError) as exc:
            error = InvalidPayload(f"payload cannot be hashed: {exc}")
            raise self._refuse(error, event, actor, run_id, approval, action=action) from exc

    def _check_launch_payload(
        self,
        run: _Run,
        action: str,
        payload: BaseModel,
        digest: str,
        event: AuditEvent,
        actor: str,
        run_id: str,
        *,
        from_state: State | None = None,
        to_state: State | None = None,
    ) -> None:
        """The one place the launch rule lives: a launch payload must be a LaunchPayload whose
        strategy hash is the run's approved strategy. Other actions pass through."""
        if action != APPROVE_LAUNCH:
            return
        error: ApprovalError
        if not isinstance(payload, LaunchPayload):
            error = InvalidPayload("a launch approval payload must carry strategy_payload_hash")
        elif payload.strategy_payload_hash != run.approved_strategy_hash:
            error = StrategyMismatch("launch payload does not match the approved strategy")
        else:
            return
        raise self._refuse(
            error,
            event,
            actor,
            run_id,
            payload_hash=digest,
            from_state=from_state,
            to_state=to_state,
            action=action,
        )

    def _verify_gate(
        self,
        run: _Run,
        run_id: str,
        src: State,
        dst: State,
        action: str,
        payload: BaseModel | None,
        actor: str,
    ) -> tuple[Approval, str]:
        """Check the newest approval for this run and action against the presented payload."""
        event: AuditEvent = "transition"
        error: ApprovalError
        if payload is None:
            error = InvalidPayload("this move needs the payload that was approved")
            raise self._refuse(
                error, event, actor, run_id, from_state=src, to_state=dst, action=action
            )
        digest = self._hash_or_refuse(payload, event, actor, run_id, action)
        self._check_launch_payload(
            run, action, payload, digest, event, actor, run_id, from_state=src, to_state=dst
        )
        approval = self._newest(run_id, action)
        if approval is None:
            error = ApprovalMissing("no approval for this move")
            raise self._refuse(
                error,
                event,
                actor,
                run_id,
                from_state=src,
                to_state=dst,
                action=action,
                payload_hash=digest,
            )
        approval = self._require_granted(
            self._refresh(approval), event, actor, digest, from_state=src, to_state=dst
        )
        if digest != approval.payload_hash:
            error = PayloadMismatch("payload differs from the approved one")
            raise self._refuse(
                error, event, actor, run_id, approval, digest, from_state=src, to_state=dst
            )
        return approval, digest

    def _newest(self, run_id: str, action: str) -> Approval | None:
        for approval in reversed(list(self._approvals.values())):
            if approval.run_id == run_id and approval.action == action:
                return approval
        return None

    def _refresh(self, approval: Approval) -> Approval:
        """Lazily mark an approval expired once the clock reaches its expiry (at or after)."""
        live = (ApprovalStatus.PENDING, ApprovalStatus.GRANTED)
        if approval.status in live and self._clock.now() >= approval.expires_at:
            approval = approval.model_copy(update={"status": ApprovalStatus.EXPIRED})
            self._approvals[approval.approval_id] = approval
        return approval

    def _require_granted(
        self,
        approval: Approval,
        event: AuditEvent,
        actor: str,
        digest: str,
        *,
        from_state: State | None = None,
        to_state: State | None = None,
    ) -> Approval:
        problems: dict[ApprovalStatus, ApprovalError] = {
            ApprovalStatus.DENIED: ApprovalDenied("approval was denied"),
            ApprovalStatus.CONSUMED: ApprovalAlreadyUsed("approval was already used"),
            ApprovalStatus.EXPIRED: ApprovalExpired("approval expired"),
            ApprovalStatus.PENDING: ApprovalPending("approval has not been decided yet"),
        }
        error = problems.get(approval.status)
        if error is not None:
            raise self._refuse(
                error, event, actor, approval.run_id, approval, digest,
                from_state=from_state, to_state=to_state,
            )  # fmt: skip
        return approval

    def _spend(self, approval: Approval, actor: str) -> Approval:
        spent = approval.model_copy(update={"status": ApprovalStatus.CONSUMED})
        self._approvals[approval.approval_id] = spent
        self._log("approval_consumed", actor, run_id=approval.run_id, approval=spent)
        return spent

    def _refuse(
        self,
        error: Exception,
        event: AuditEvent,
        actor: str,
        run_id: str | None = None,
        approval: Approval | None = None,
        payload_hash: str | None = None,
        *,
        from_state: State | None = None,
        to_state: State | None = None,
        action: str | None = None,
        approval_id: str | None = None,
    ) -> Exception:
        """Audit a refusal and hand the error back for the caller to raise."""
        self._log(
            event,
            actor,
            outcome="refused",
            run_id=run_id,
            from_state=from_state,
            to_state=to_state,
            approval=approval,
            action=action,
            approval_id=approval_id,
            payload_hash=payload_hash,
            detail=type(error).__name__,
        )
        return error

    def _log(
        self,
        event: AuditEvent,
        actor: str,
        *,
        outcome: Literal["ok", "refused"] = "ok",
        run_id: str | None = None,
        from_state: State | None = None,
        to_state: State | None = None,
        approval: Approval | None = None,
        action: str | None = None,
        approval_id: str | None = None,
        payload_hash: str | None = None,
        detail: str | None = None,
    ) -> None:
        self.audit.append(
            AuditRecord(
                seq=self.audit.next_seq(),
                at=self._clock.now(),
                event=event,
                outcome=outcome,
                actor=actor,
                run_id=run_id,
                from_state=from_state,
                to_state=to_state,
                approval_id=approval.approval_id if approval else approval_id,
                action=approval.action if approval else action,
                payload_hash=payload_hash or (approval.payload_hash if approval else None),
                detail=detail,
            )
        )
