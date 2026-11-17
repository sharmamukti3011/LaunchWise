"""ApprovalService: state machine, approvals bound to payload hashes, audit log. All in memory."""

from datetime import timedelta
from decimal import Decimal

import pytest
from pydantic import BaseModel, ValidationError

from app.engine.approval_payload import hash_model
from app.engine.approval_rules import InvalidTransition, State
from app.services.approvals import (
    ActionMismatch,
    Approval,
    ApprovalAlreadyUsed,
    ApprovalDenied,
    ApprovalError,
    ApprovalExpired,
    ApprovalMissing,
    ApprovalNotPending,
    ApprovalPending,
    ApprovalService,
    ApprovalStatus,
    AuditLog,
    AuditRecord,
    InvalidPayload,
    LaunchPayload,
    PayloadMismatch,
    RunExists,
    RunMismatch,
    RunNotFound,
    StrategyMismatch,
    UnknownAction,
    WrongState,
)
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


def make_service(clock: FakeClock, **kwargs: object) -> ApprovalService:
    counter = iter(range(1, 1000))
    return ApprovalService(clock, id_factory=lambda: f"ap-{next(counter)}", **kwargs)  # type: ignore[arg-type]


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def svc(clock: FakeClock) -> ApprovalService:
    return make_service(clock)


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


# ---- runs and plain transitions ---------------------------------------------------------------


def test_start_run_begins_in_draft_and_is_audited(svc: ApprovalService) -> None:
    assert svc.start_run("r1", "agent") == S.DRAFT
    assert svc.state_of("r1") == S.DRAFT
    assert events(svc) == [("run_started", "ok")]


def test_duplicate_run_and_unknown_run_are_rejected(svc: ApprovalService) -> None:
    svc.start_run("r1", "agent")
    with pytest.raises(RunExists):
        svc.start_run("r1", "agent")
    with pytest.raises(RunNotFound):
        svc.state_of("nope")
    with pytest.raises(RunNotFound):
        svc.transition("nope", S.STRATEGY_PROPOSED, "agent")


def test_ungated_transition_moves_state_and_is_audited(svc: ApprovalService) -> None:
    svc.start_run("r1", "agent")
    assert svc.transition("r1", S.STRATEGY_PROPOSED, "agent") == S.STRATEGY_PROPOSED
    record = svc.audit.records[-1]
    assert (record.event, record.from_state, record.to_state) == (
        "transition",
        S.DRAFT,
        S.STRATEGY_PROPOSED,
    )


def test_invalid_transition_raises_leaves_state_and_is_audited_as_refused(
    svc: ApprovalService,
) -> None:
    svc.start_run("r1", "agent")
    with pytest.raises(InvalidTransition):
        svc.transition("r1", S.LIVE, "agent")
    assert svc.state_of("r1") == S.DRAFT
    record = svc.audit.records[-1]
    assert (record.event, record.outcome, record.detail) == (
        "transition",
        "refused",
        "InvalidTransition",
    )
    assert (record.from_state, record.to_state) == (S.DRAFT, S.LIVE)


# ---- request_approval -------------------------------------------------------------------------


def test_request_binds_the_hash_of_the_payload_and_sets_expiry(
    svc: ApprovalService, clock: FakeClock
) -> None:
    to_proposed(svc)
    approval = svc.request_approval("r1", STRATEGY, strategy(), "agent")
    assert approval.payload_hash == hash_model(strategy())
    assert approval.status == ApprovalStatus.PENDING
    assert approval.created_at == clock.now()
    assert approval.expires_at - approval.created_at == TTL  # default TTL is 15 minutes


def test_ttl_is_a_constructor_argument(clock: FakeClock) -> None:
    short = make_service(clock, ttl=timedelta(minutes=1))
    to_proposed(short)
    approval = short.request_approval("r1", STRATEGY, strategy(), "agent")
    assert approval.expires_at - approval.created_at == timedelta(minutes=1)


def test_request_rejects_unknown_action_and_wrong_state(svc: ApprovalService) -> None:
    svc.start_run("r1", "agent")
    with pytest.raises(UnknownAction):
        svc.request_approval("r1", "delete_everything", strategy(), "agent")
    with pytest.raises(WrongState):  # strategy approval only makes sense once proposed
        svc.request_approval("r1", STRATEGY, strategy(), "agent")
    with pytest.raises(RunNotFound):
        svc.request_approval("nope", STRATEGY, strategy(), "agent")
    assert all(r.outcome == "refused" for r in svc.audit.records[1:])


def test_launch_request_must_carry_the_approved_strategy_hash(svc: ApprovalService) -> None:
    to_strategy_approved(svc, strategy())
    with pytest.raises(InvalidPayload):  # not a LaunchPayload at all
        svc.request_approval("r1", LAUNCH, strategy(), "agent")
    with pytest.raises(StrategyMismatch):
        svc.request_approval("r1", LAUNCH, launch_for(strategy(option_id="other")), "agent")


# ---- decide: records the decision only --------------------------------------------------------


def test_decide_records_the_decision_and_never_moves_run_state(svc: ApprovalService) -> None:
    to_proposed(svc)
    approval = svc.request_approval("r1", STRATEGY, strategy(), "agent")
    decided = svc.decide(approval.approval_id, strategy(), True, "user")
    assert decided.status == ApprovalStatus.GRANTED
    assert decided.decided_by == "user"
    assert svc.state_of("r1") == S.STRATEGY_PROPOSED  # unchanged until transition()
    assert not any(
        r.event == "transition" and r.to_state == S.STRATEGY_APPROVED for r in svc.audit.records
    )


def test_denied_decision_is_recorded_and_also_leaves_state(svc: ApprovalService) -> None:
    to_proposed(svc)
    approval = approve(svc, STRATEGY, strategy(), grant=False)
    assert svc.get_approval(approval.approval_id).status == ApprovalStatus.DENIED
    assert svc.state_of("r1") == S.STRATEGY_PROPOSED
    assert svc.audit.records[-1].detail == "denied"


def test_decide_with_a_different_payload_is_refused_and_stays_pending(
    svc: ApprovalService,
) -> None:
    to_proposed(svc)
    approval = svc.request_approval("r1", STRATEGY, strategy(), "agent")
    with pytest.raises(PayloadMismatch):
        svc.decide(approval.approval_id, strategy(price=Decimal("999")), True, "user")
    assert svc.get_approval(approval.approval_id).status == ApprovalStatus.PENDING
    assert svc.audit.records[-1].outcome == "refused"


def test_decide_twice_and_decide_unknown_are_refused(svc: ApprovalService) -> None:
    to_proposed(svc)
    approval = approve(svc, STRATEGY, strategy())
    with pytest.raises(ApprovalNotPending):
        svc.decide(approval.approval_id, strategy(), False, "user")
    assert svc.get_approval(approval.approval_id).status == ApprovalStatus.GRANTED
    with pytest.raises(ApprovalMissing):
        svc.decide("ap-unknown", strategy(), True, "user")


def test_decide_after_expiry_is_refused_and_marks_it_expired(
    svc: ApprovalService, clock: FakeClock
) -> None:
    to_proposed(svc)
    approval = svc.request_approval("r1", STRATEGY, strategy(), "agent")
    clock.advance(TTL)
    with pytest.raises(ApprovalExpired):
        svc.decide(approval.approval_id, strategy(), True, "user")
    assert svc.get_approval(approval.approval_id).status == ApprovalStatus.EXPIRED


# ---- gated transitions: payload is verified against the granted approval ----------------------


def test_strategy_transition_with_matching_payload_succeeds_and_consumes(
    svc: ApprovalService,
) -> None:
    approval = to_strategy_approved(svc, strategy())
    assert svc.state_of("r1") == S.STRATEGY_APPROVED
    assert svc.get_approval(approval.approval_id).status == ApprovalStatus.CONSUMED
    assert svc.approved_strategy_hash("r1") == hash_model(strategy())


def test_approve_payload_a_then_transition_with_payload_b_raises_payload_mismatch(
    svc: ApprovalService,
) -> None:
    to_proposed(svc)
    approval = approve(svc, STRATEGY, strategy())
    with pytest.raises(PayloadMismatch):
        svc.transition("r1", S.STRATEGY_APPROVED, "user", strategy(price=Decimal("1")))
    assert svc.state_of("r1") == S.STRATEGY_PROPOSED
    # A failed attempt does not burn the approval: the right payload still works.
    assert svc.get_approval(approval.approval_id).status == ApprovalStatus.GRANTED
    svc.transition("r1", S.STRATEGY_APPROVED, "user", strategy())
    assert svc.state_of("r1") == S.STRATEGY_APPROVED


def test_gated_transition_requires_a_payload(svc: ApprovalService) -> None:
    to_proposed(svc)
    approve(svc, STRATEGY, strategy())
    with pytest.raises(InvalidPayload):
        svc.transition("r1", S.STRATEGY_APPROVED, "user")
    assert svc.state_of("r1") == S.STRATEGY_PROPOSED


def test_gated_transition_without_a_usable_approval_is_refused(svc: ApprovalService) -> None:
    to_proposed(svc)
    with pytest.raises(ApprovalMissing):
        svc.transition("r1", S.STRATEGY_APPROVED, "user", strategy())
    svc.request_approval("r1", STRATEGY, strategy(), "agent")
    with pytest.raises(ApprovalPending):
        svc.transition("r1", S.STRATEGY_APPROVED, "user", strategy())
    assert svc.state_of("r1") == S.STRATEGY_PROPOSED


def test_denied_approval_cannot_be_used_to_transition(svc: ApprovalService) -> None:
    to_proposed(svc)
    approve(svc, STRATEGY, strategy(), grant=False)
    with pytest.raises(ApprovalDenied):
        svc.transition("r1", S.STRATEGY_APPROVED, "user", strategy())


def test_expired_granted_approval_cannot_be_used_to_transition(
    svc: ApprovalService, clock: FakeClock
) -> None:
    to_proposed(svc)
    approval = approve(svc, STRATEGY, strategy())
    clock.advance(TTL)
    with pytest.raises(ApprovalExpired):
        svc.transition("r1", S.STRATEGY_APPROVED, "user", strategy())
    assert svc.state_of("r1") == S.STRATEGY_PROPOSED
    assert svc.get_approval(approval.approval_id).status == ApprovalStatus.EXPIRED


def test_strategy_approval_is_single_use_across_a_restart_of_the_flow(
    svc: ApprovalService,
) -> None:
    to_strategy_approved(svc, strategy())
    svc.transition("r1", S.DRAFT, "user")
    svc.transition("r1", S.STRATEGY_PROPOSED, "agent")
    with pytest.raises(ApprovalAlreadyUsed):
        svc.transition("r1", S.STRATEGY_APPROVED, "user", strategy())


def test_approvals_are_per_run(svc: ApprovalService) -> None:
    to_proposed(svc, "r1")
    to_proposed(svc, "r2")
    approve(svc, STRATEGY, strategy(), "r1")
    with pytest.raises(ApprovalMissing):
        svc.transition("r2", S.STRATEGY_APPROVED, "user", strategy())


# ---- launch approval chains to the approved strategy ------------------------------------------


def test_launch_transition_verifies_but_does_not_consume_the_approval(
    svc: ApprovalService,
) -> None:
    approval = to_launch_approved(svc, strategy())
    assert svc.state_of("r1") == S.LAUNCH_APPROVED
    assert svc.get_approval(approval.approval_id).status == ApprovalStatus.GRANTED


def test_launch_transition_refuses_a_payload_that_differs_from_the_approved_one(
    svc: ApprovalService,
) -> None:
    to_strategy_approved(svc, strategy())
    approve(svc, LAUNCH, launch_for(strategy()))
    with pytest.raises(PayloadMismatch):
        svc.transition("r1", S.LAUNCH_APPROVED, "user", launch_for(strategy(), title="Other"))
    assert svc.state_of("r1") == S.STRATEGY_APPROVED


def test_launch_transition_refuses_a_payload_without_the_strategy_hash(
    svc: ApprovalService,
) -> None:
    to_strategy_approved(svc, strategy())
    approve(svc, LAUNCH, launch_for(strategy()))
    with pytest.raises(InvalidPayload):
        svc.transition("r1", S.LAUNCH_APPROVED, "user", strategy())
    assert svc.state_of("r1") == S.STRATEGY_APPROVED


def test_strategy_changed_after_approval_makes_the_old_launch_approval_unusable(
    svc: ApprovalService,
) -> None:
    to_strategy_approved(svc, strategy())
    old_launch = launch_for(strategy())
    approve(svc, LAUNCH, old_launch)  # granted against strategy S1
    # The strategy is revised and re-approved with different content (S2).
    svc.transition("r1", S.DRAFT, "user")
    svc.transition("r1", S.STRATEGY_PROPOSED, "agent")
    revised = strategy(price=Decimal("900"))
    approve(svc, STRATEGY, revised)
    svc.transition("r1", S.STRATEGY_APPROVED, "user", revised)
    with pytest.raises(StrategyMismatch):
        svc.transition("r1", S.LAUNCH_APPROVED, "user", old_launch)
    assert svc.state_of("r1") == S.STRATEGY_APPROVED


# ---- deploy edge: the approval is consumed by the move into DEPLOYING -------------------------


def test_deploying_requires_and_consumes_the_launch_approval(svc: ApprovalService) -> None:
    approval = to_launch_approved(svc, strategy())
    assert svc.transition("r1", S.DEPLOYING, "deployer", launch_for(strategy())) == S.DEPLOYING
    assert svc.get_approval(approval.approval_id).status == ApprovalStatus.CONSUMED
    assert svc.transition("r1", S.LIVE, "deployer") == S.LIVE


def test_deploying_without_payload_or_with_a_different_one_is_refused(
    svc: ApprovalService,
) -> None:
    to_launch_approved(svc, strategy())
    with pytest.raises(InvalidPayload):
        svc.transition("r1", S.DEPLOYING, "deployer")
    with pytest.raises(PayloadMismatch):
        svc.transition("r1", S.DEPLOYING, "deployer", launch_for(strategy(), title="Other"))
    assert svc.state_of("r1") == S.LAUNCH_APPROVED


def test_deploying_after_the_launch_approval_expired_is_refused(
    svc: ApprovalService, clock: FakeClock
) -> None:
    to_launch_approved(svc, strategy())
    clock.advance(TTL)
    with pytest.raises(ApprovalExpired):
        svc.transition("r1", S.DEPLOYING, "deployer", launch_for(strategy()))
    assert svc.state_of("r1") == S.LAUNCH_APPROVED


def test_failed_deploy_leaves_the_approval_consumed(svc: ApprovalService) -> None:
    approval = to_launch_approved(svc, strategy())
    svc.transition("r1", S.DEPLOYING, "deployer", launch_for(strategy()))
    svc.transition("r1", S.FAILED, "deployer")
    assert svc.get_approval(approval.approval_id).status == ApprovalStatus.CONSUMED


# ---- consume (direct) -------------------------------------------------------------------------


def test_consume_succeeds_once_then_is_already_used(svc: ApprovalService) -> None:
    to_proposed(svc)
    approval = approve(svc, STRATEGY, strategy())
    consumed = svc.consume(approval.approval_id, "r1", STRATEGY, strategy(), "deployer")
    assert consumed.status == ApprovalStatus.CONSUMED
    with pytest.raises(ApprovalAlreadyUsed):
        svc.consume(approval.approval_id, "r1", STRATEGY, strategy(), "deployer")


def test_consume_checks_payload_action_run_and_status(svc: ApprovalService) -> None:
    to_proposed(svc, "r1")
    svc.start_run("r2", "agent")
    pending = svc.request_approval("r1", STRATEGY, strategy(), "agent")
    with pytest.raises(ApprovalPending):
        svc.consume(pending.approval_id, "r1", STRATEGY, strategy(), "x")
    svc.decide(pending.approval_id, strategy(), True, "user")
    with pytest.raises(PayloadMismatch):
        svc.consume(pending.approval_id, "r1", STRATEGY, strategy(option_id="z"), "x")
    with pytest.raises(ActionMismatch):
        svc.consume(pending.approval_id, "r1", LAUNCH, strategy(), "x")
    with pytest.raises(RunMismatch):
        svc.consume(pending.approval_id, "r2", STRATEGY, strategy(), "x")
    with pytest.raises(ApprovalMissing):
        svc.consume("ap-unknown", "r1", STRATEGY, strategy(), "x")
    # None of those refusals used the approval up.
    assert svc.get_approval(pending.approval_id).status == ApprovalStatus.GRANTED


def test_consume_denied_is_refused(svc: ApprovalService) -> None:
    to_proposed(svc)
    approval = approve(svc, STRATEGY, strategy(), grant=False)
    with pytest.raises(ApprovalDenied):
        svc.consume(approval.approval_id, "r1", STRATEGY, strategy(), "x")


def test_expiry_boundary_one_second_before_works_at_expiry_fails(clock: FakeClock) -> None:
    for offset, should_work in [(TTL - timedelta(seconds=1), True), (TTL, False)]:
        svc = make_service(clock)
        to_proposed(svc)
        approval = approve(svc, STRATEGY, strategy())
        clock.advance(offset)
        if should_work:
            svc.consume(approval.approval_id, "r1", STRATEGY, strategy(), "x")
        else:
            with pytest.raises(ApprovalExpired):
                svc.consume(approval.approval_id, "r1", STRATEGY, strategy(), "x")
        clock.advance(-offset)


# ---- one hash through every path --------------------------------------------------------------


def test_the_same_model_hashes_the_same_through_request_decide_transition_and_consume(
    svc: ApprovalService,
) -> None:
    strat = strategy()
    # Same content, set-like list in another order: must still be the same payload.
    reordered = strategy(skills=["decorating", "baking"])
    to_proposed(svc)
    approval = svc.request_approval("r1", STRATEGY, strat, "agent")  # request
    svc.decide(approval.approval_id, reordered, True, "user")  # decide
    svc.transition("r1", S.STRATEGY_APPROVED, "user", reordered)  # transition (consumes)
    expected = hash_model(strat)
    assert approval.payload_hash == expected
    mine = [r for r in svc.audit.records if r.approval_id == approval.approval_id]
    assert [r.event for r in mine] == [
        "approval_requested",
        "approval_decided",
        "approval_consumed",
        "transition",
    ]
    assert {r.payload_hash for r in mine} == {expected}

    launch = launch_for(strat)
    second = approve(svc, LAUNCH, launch)
    svc.consume(second.approval_id, "r1", LAUNCH, launch, "deployer")  # consume
    mine = [r for r in svc.audit.records if r.approval_id == second.approval_id]
    assert {r.payload_hash for r in mine} == {hash_model(launch)}


# ---- audit log --------------------------------------------------------------------------------


def test_happy_path_audit_trail_is_complete_and_ordered(svc: ApprovalService) -> None:
    to_strategy_approved(svc, strategy())
    assert events(svc) == [
        ("run_started", "ok"),
        ("transition", "ok"),
        ("approval_requested", "ok"),
        ("approval_decided", "ok"),
        ("approval_consumed", "ok"),
        ("transition", "ok"),
    ]
    assert [r.seq for r in svc.audit.records] == [1, 2, 3, 4, 5, 6]


def test_audit_timestamps_come_from_the_injected_clock(
    svc: ApprovalService, clock: FakeClock
) -> None:
    svc.start_run("r1", "agent")
    first = clock.now()
    clock.advance(timedelta(seconds=30))
    svc.transition("r1", S.STRATEGY_PROPOSED, "agent")
    assert [r.at for r in svc.audit.records] == [first, clock.now()]


def test_every_refusal_is_audited_with_a_stable_reason(svc: ApprovalService) -> None:
    to_proposed(svc)
    approval = approve(svc, STRATEGY, strategy())
    before = len(svc.audit.records)
    attempts: list[tuple[type[ApprovalError], object]] = [
        (
            PayloadMismatch,
            lambda: svc.transition("r1", S.STRATEGY_APPROVED, "u", strategy(option_id="q")),
        ),
        (InvalidPayload, lambda: svc.transition("r1", S.STRATEGY_APPROVED, "u")),
        (ActionMismatch, lambda: svc.consume(approval.approval_id, "r1", LAUNCH, strategy(), "u")),
        (ApprovalNotPending, lambda: svc.decide(approval.approval_id, strategy(), True, "u")),
    ]
    for error, call in attempts:
        with pytest.raises(error):
            call()  # type: ignore[operator]
    new = svc.audit.records[before:]
    assert [r.outcome for r in new] == ["refused"] * len(attempts)
    assert [r.detail for r in new] == [error.__name__ for error, _ in attempts]


def test_audit_log_is_read_only_to_callers(svc: ApprovalService) -> None:
    svc.start_run("r1", "agent")
    records = svc.audit.records
    assert isinstance(records, tuple)
    with pytest.raises(ValidationError):
        records[0].__setattr__("outcome", "refused")
    assert svc.audit.records[0].outcome == "ok"


def test_audit_log_holds_hashes_never_payload_content(svc: ApprovalService) -> None:
    to_strategy_approved(svc, strategy())
    dump = " ".join(r.model_dump_json() for r in svc.audit.records)
    assert "opt-marker-7" not in dump
    assert "decorating" not in dump


def test_audit_log_append_enforces_a_gapless_sequence(clock: FakeClock) -> None:
    log = AuditLog()
    assert log.next_seq() == 1

    def record(seq: int) -> AuditRecord:
        return AuditRecord(seq=seq, at=clock.now(), event="run_started", outcome="ok", actor="a")

    log.append(record(1))
    assert log.next_seq() == 2
    with pytest.raises(ValueError, match="seq"):
        log.append(record(5))  # gap
    with pytest.raises(ValueError, match="seq"):
        log.append(record(1))  # duplicate
    assert [r.seq for r in log.records] == [1]


def test_service_can_share_an_injected_audit_log(clock: FakeClock) -> None:
    log = AuditLog()
    svc = ApprovalService(clock, audit=log)
    svc.start_run("r1", "agent")
    assert svc.audit is log
    assert len(log.records) == 1
