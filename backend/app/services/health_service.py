from collections.abc import Callable
from datetime import UTC, datetime

from app.schemas.health import HealthResponse
from app.settings import Settings


def _utc_now() -> datetime:
    return datetime.now(UTC)


class HealthService:
    """Clock is injected so tests can pass a fixed time."""

    def __init__(self, settings: Settings, clock: Callable[[], datetime] = _utc_now) -> None:
        self._settings = settings
        self._clock = clock

    def status(self) -> HealthResponse:
        return HealthResponse(
            status="ok",
            environment=self._settings.app_env,
            checked_at=self._clock(),
        )
