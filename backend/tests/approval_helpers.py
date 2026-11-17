"""Shared builders for approval tests: payload models, services, and flow shortcuts."""

from datetime import timedelta
from decimal import Decimal

from pydantic import BaseModel

from app.engine.approval_payload import hash_model
from app.engine.approval_rules import State
from app.services.approvals import Approval, ApprovalService, LaunchPayload
from tests.fakes import FakeClock

S = State
STRATEGY = "approve_strategy"
LAUNCH = "approve_launch"
TTL = timedelta(minutes=15)


class Strategy(BaseModel):
    option_id: str
    price: Decimal
    skills: list[str]


class Launch(LaunchPayload):
    site_title: str


def strategy(**overrides: object) -> Strategy:
    data: dict[str, object] = {
        "option_id": "opt-marker-7",
        "price": Decimal("800"),
        "skills": ["baking", "decorating"],
    }
    data.update(overrides)
    return Strategy.model_validate(data)


def launch_for(strat: Strategy, title: str = "Weekend cakes") -> Launch:
    return Launch(strategy_payload_hash=hash_model(strat), site_title=title)


def make_service(clock: FakeClock, ttl: timedelta = TTL) -> ApprovalService:
    """A service with a fake clock and predictable approval ids (ap-1, ap-2, ...)."""
    counter = iter(range(1, 1000))
    return ApprovalService(clock, ttl=ttl, id_factory=lambda: f"ap-{next(counter)}")


def approve(
    svc: ApprovalService, action: str, payload: BaseModel, run: str = "r1", grant: bool = True
) -> Approval:
    approval = svc.request_approval(run, action, payload, "agent")
    svc.decide(approval.approval_id, payload, grant, "user")
    return approval


def to_proposed(svc: ApprovalService, run: str = "r1") -> None:
    svc.start_run(run, "agent")
    svc.transition(run, S.STRATEGY_PROPOSED, "agent")


def to_strategy_approved(svc: ApprovalService, strat: Strategy, run: str = "r1") -> Approval:
    to_proposed(svc, run)
    approval = approve(svc, STRATEGY, strat, run)
    svc.transition(run, S.STRATEGY_APPROVED, "user", strat)
    return approval


def to_launch_approved(svc: ApprovalService, strat: Strategy, run: str = "r1") -> Approval:
    to_strategy_approved(svc, strat, run)
    approval = approve(svc, LAUNCH, launch_for(strat), run)
    svc.transition(run, S.LAUNCH_APPROVED, "user", launch_for(strat))
    return approval


def events(svc: ApprovalService) -> list[tuple[str, str]]:
    return [(r.event, r.outcome) for r in svc.audit.records]
