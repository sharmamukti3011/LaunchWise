"""Fixtures shared across test modules."""

import pytest

from app.services.approvals import ApprovalService
from tests.approval_helpers import make_service
from tests.fakes import FakeClock


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def svc(clock: FakeClock) -> ApprovalService:
    return make_service(clock)
