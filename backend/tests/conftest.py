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


@pytest.fixture(autouse=True)
def _no_real_claude_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    """A real key in the developer's shell must never reach a test, or make it call the network."""
    for name in ("ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "CLAUDE_MODEL"):
        monkeypatch.delenv(name, raising=False)
