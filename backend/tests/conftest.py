"""Fixtures shared across test modules."""

import socket
from typing import Any

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


@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """No test may open a network connection, so none can ever send a real email."""

    def refuse(*args: Any, **kwargs: Any) -> None:
        raise RuntimeError("tests must not open network connections")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket.socket, "connect_ex", refuse)
