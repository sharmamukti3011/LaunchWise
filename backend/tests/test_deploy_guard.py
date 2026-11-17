"""DeployGuard: a thin wrapper. The approval check lives in transition(DEPLOYING, payload)."""

import threading
import time
from datetime import datetime, timedelta

import pytest

from app.engine.approval_rules import InvalidTransition, State
from app.services.approvals import (
    ApprovalError,
    ApprovalExpired,
    ApprovalService,
    ApprovalStatus,
    InvalidPayload,
    LaunchPayload,
    PayloadMismatch,
    RunNotFound,
    StrategyMismatch,
)
from app.services.deploy_guard import DeployError, DeployFailed, DeployGuard
from tests.approval_helpers import (
    TTL,
    S,
    events,
    launch_for,
    make_service,
    strategy,
    to_launch_approved,
    to_strategy_approved,
)
from tests.fakes import FakeClock, FakeDeployer

# ---- happy path and ordering ------------------------------------------------------------------


def test_deploy_goes_live_calls_the_deployer_once_and_audits_the_steps(
    svc: ApprovalService,
) -> None:
    to_launch_approved(svc, strategy())
    before = len(svc.audit.records)
    deployer = FakeDeployer()
    payload = launch_for(strategy())

    assert DeployGuard(svc, deployer).deploy("r1", payload, "deployer") == S.LIVE

    assert svc.state_of("r1") == S.LIVE
    assert deployer.calls == [("r1", payload)]
    new = svc.audit.records[before:]
    assert [(r.event, r.to_state) for r in new] == [
        ("approval_consumed", None),
        ("transition", S.DEPLOYING),
        ("transition", S.LIVE),
    ]
    assert all(r.outcome == "ok" for r in new)


def test_the_deployer_runs_only_after_the_approval_is_spent(svc: ApprovalService) -> None:
    approval = to_launch_approved(svc, strategy())
    seen: list[tuple[State, ApprovalStatus]] = []

    def inspect(run_id: str, payload: LaunchPayload) -> None:
        seen.append((svc.state_of(run_id), svc.get_approval(approval.approval_id).status))

    DeployGuard(svc, FakeDeployer(on_call=inspect)).deploy("r1", launch_for(strategy()), "d")
    assert seen == [(S.DEPLOYING, ApprovalStatus.CONSUMED)]


def test_deploy_works_one_second_before_the_approval_expires(
    svc: ApprovalService, clock: FakeClock
) -> None:
    to_launch_approved(svc, strategy())
    clock.advance(TTL - timedelta(seconds=1))
    assert DeployGuard(svc, FakeDeployer()).deploy("r1", launch_for(strategy()), "d") == S.LIVE


# ---- refusals: the deployer is never called ---------------------------------------------------


def _assert_refused(
    svc: ApprovalService, deployer: FakeDeployer, error: type[Exception], before: State | None
) -> None:
    assert deployer.calls == []
    if before is not None:
        assert svc.state_of("r1") == before
    last = svc.audit.records[-1]
    assert (last.outcome, last.detail) == ("refused", error.__name__)


def test_refuses_when_the_run_is_not_launch_approved(svc: ApprovalService) -> None:
    deployer = FakeDeployer()
    guard = DeployGuard(svc, deployer)
    svc.start_run("r1", "agent")
    with pytest.raises(InvalidTransition):
        guard.deploy("r1", launch_for(strategy()), "d")
    _assert_refused(svc, deployer, InvalidTransition, S.DRAFT)

    svc2 = make_service(FakeClock())
    to_strategy_approved(svc2, strategy())
    deployer2 = FakeDeployer()
    with pytest.raises(InvalidTransition):
        DeployGuard(svc2, deployer2).deploy("r1", launch_for(strategy()), "d")
    _assert_refused(svc2, deployer2, InvalidTransition, S.STRATEGY_APPROVED)


def test_refuses_an_unknown_run(svc: ApprovalService) -> None:
    deployer = FakeDeployer()
    with pytest.raises(RunNotFound):
        DeployGuard(svc, deployer).deploy("nope", launch_for(strategy()), "d")
    _assert_refused(svc, deployer, RunNotFound, None)


def test_refuses_an_expired_launch_approval(svc: ApprovalService, clock: FakeClock) -> None:
    to_launch_approved(svc, strategy())
    clock.advance(TTL)  # at expiry, not after
    deployer = FakeDeployer()
    with pytest.raises(ApprovalExpired):
        DeployGuard(svc, deployer).deploy("r1", launch_for(strategy()), "d")
    _assert_refused(svc, deployer, ApprovalExpired, S.LAUNCH_APPROVED)


def test_refuses_a_payload_that_differs_from_the_approved_one(svc: ApprovalService) -> None:
    to_launch_approved(svc, strategy())
    deployer = FakeDeployer()
    with pytest.raises(PayloadMismatch):
        DeployGuard(svc, deployer).deploy("r1", launch_for(strategy(), title="Tampered"), "d")
    _assert_refused(svc, deployer, PayloadMismatch, S.LAUNCH_APPROVED)


def test_refuses_a_payload_built_on_a_different_strategy(svc: ApprovalService) -> None:
    to_launch_approved(svc, strategy())
    deployer = FakeDeployer()
    with pytest.raises(StrategyMismatch):
        DeployGuard(svc, deployer).deploy("r1", launch_for(strategy(option_id="other")), "d")
    _assert_refused(svc, deployer, StrategyMismatch, S.LAUNCH_APPROVED)


def test_refuses_a_payload_that_is_not_a_launch_payload(svc: ApprovalService) -> None:
    to_launch_approved(svc, strategy())
    deployer = FakeDeployer()
    with pytest.raises(InvalidPayload):
        DeployGuard(svc, deployer).deploy("r1", strategy(), "d")  # type: ignore[arg-type]
    _assert_refused(svc, deployer, InvalidPayload, S.LAUNCH_APPROVED)


def test_a_refused_deploy_does_not_burn_the_approval(svc: ApprovalService) -> None:
    approval = to_launch_approved(svc, strategy())
    guard = DeployGuard(svc, FakeDeployer())
    with pytest.raises(PayloadMismatch):
        guard.deploy("r1", launch_for(strategy(), title="Tampered"), "d")
    assert svc.get_approval(approval.approval_id).status == ApprovalStatus.GRANTED
    assert guard.deploy("r1", launch_for(strategy()), "d") == S.LIVE


# ---- single use -------------------------------------------------------------------------------


def test_second_deploy_after_success_is_refused_and_the_deployer_is_not_called_again(
    svc: ApprovalService,
) -> None:
    to_launch_approved(svc, strategy())
    deployer = FakeDeployer()
    guard = DeployGuard(svc, deployer)
    guard.deploy("r1", launch_for(strategy()), "d")
    with pytest.raises(InvalidTransition):
        guard.deploy("r1", launch_for(strategy()), "d")
    assert len(deployer.calls) == 1
    assert svc.state_of("r1") == S.LIVE
    assert events(svc)[-1] == ("transition", "refused")


# ---- deployer failure -------------------------------------------------------------------------


@pytest.mark.parametrize("failure", [DeployError("boom"), RuntimeError("secret path /srv/x")])
def test_deployer_failure_ends_failed_keeps_the_approval_spent_and_chains_the_cause(
    svc: ApprovalService, failure: Exception
) -> None:
    approval = to_launch_approved(svc, strategy())
    deployer = FakeDeployer(fail_with=failure)
    guard = DeployGuard(svc, deployer)

    with pytest.raises(DeployFailed) as raised:
        guard.deploy("r1", launch_for(strategy()), "d")

    assert raised.value.__cause__ is failure
    assert svc.state_of("r1") == S.FAILED
    assert svc.get_approval(approval.approval_id).status == ApprovalStatus.CONSUMED
    last = svc.audit.records[-1]
    assert (last.event, last.to_state, last.outcome) == ("transition", S.FAILED, "ok")
    assert last.detail == type(failure).__name__
    # Only the class name is logged; the message (which may hold paths or secrets) is not.
    assert "secret path" not in " ".join(r.model_dump_json() for r in svc.audit.records)

    with pytest.raises(InvalidTransition):  # FAILED is terminal: no retry on this run
        guard.deploy("r1", launch_for(strategy()), "d")
    assert len(deployer.calls) == 1


# ---- concurrency ------------------------------------------------------------------------------


class _SlowClock(FakeClock):
    """Widens the gap between 'check the approval' and 'spend it' so a missing lock shows up."""

    def now(self) -> datetime:
        time.sleep(0.002)
        return super().now()


def test_concurrent_deploys_with_one_approval_deploy_exactly_once() -> None:
    svc = make_service(_SlowClock())
    to_launch_approved(svc, strategy())
    deployer = FakeDeployer()
    guard = DeployGuard(svc, deployer)
    threads = 8
    barrier = threading.Barrier(threads)
    outcomes: list[object] = []

    def attempt() -> None:
        barrier.wait()
        try:
            outcomes.append(guard.deploy("r1", launch_for(strategy()), "d"))
        except (ApprovalError, InvalidTransition) as exc:
            outcomes.append(exc)

    workers = [threading.Thread(target=attempt) for _ in range(threads)]
    for worker in workers:
        worker.start()
    for worker in workers:
        worker.join()

    assert len(deployer.calls) == 1
    assert outcomes.count(S.LIVE) == 1
    assert len(outcomes) == threads
    assert svc.state_of("r1") == S.LIVE


# ---- transition(detail=...) -------------------------------------------------------------------


def test_transition_detail_is_recorded_and_defaults_to_none(svc: ApprovalService) -> None:
    svc.start_run("r1", "agent")
    svc.transition("r1", S.STRATEGY_PROPOSED, "agent")
    assert svc.audit.records[-1].detail is None
    svc.transition("r1", S.DRAFT, "agent", detail="reworked")
    assert svc.audit.records[-1].detail == "reworked"
