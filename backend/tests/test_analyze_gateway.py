"""AnalyzeGateway: per-client rate limit and outcome-only logging around the analyze service."""

import logging
from datetime import timedelta
from typing import Any

import pytest

from app.services.analyze_gateway import AnalyzeGateway
from app.services.analyze_models import AnalyzeRequest
from app.services.analyze_service import AnalyzeService, ScenarioError
from app.services.market_data import MarketDataset
from app.services.rate_limit import RateLimited, RateLimiter
from tests.fakes import FakeClock
from tests.pune_fixtures import opportunity

NOIDA = "Noida, Uttar Pradesh"


def req(**overrides: Any) -> AnalyzeRequest:
    data: dict[str, Any] = {
        "profile": {
            "budget": "10000",
            "units_per_day": 3,
            "days_per_week": 2,
            "hours_per_week": {"value": 12, "source": "assumption"},
            "skills": ["baking"],
            "equipment": ["oven"],
            "location": "Pune",
        },
        "category": "home bakery",
        "options": [
            {
                "id": "original",
                "title": "Secret Cakes Ltd",
                "is_original": True,
                "price": "800",
                "variable_cost_per_unit": "350",
                "fixed_startup_costs": "3000",
                "minutes_per_unit": {"value": 60, "source": "user_provided"},
            }
        ],
    }
    data.update(overrides)
    return AnalyzeRequest.model_validate(data)


def gateway(clock: FakeClock, limit: int = 3) -> AnalyzeGateway:
    service = AnalyzeService(MarketDataset([opportunity(id="TEST-FAKE-001")]), clock)
    limiter = RateLimiter(limit=limit, window=timedelta(minutes=1), clock=clock)
    return AnalyzeGateway(service, limiter)


def test_it_delegates_to_the_service() -> None:
    result = gateway(FakeClock()).analyze(req(), "198.51.100.1")
    assert result.ranking.recommended_id == "original"


def test_each_client_has_its_own_bucket_and_the_limit_resets() -> None:
    clock = FakeClock()
    gw = gateway(clock, limit=2)
    for _ in range(2):
        gw.analyze(req(), "198.51.100.1")
    with pytest.raises(RateLimited) as refused:
        gw.analyze(req(), "198.51.100.1")
    assert refused.value.retry_after == 60
    gw.analyze(req(), "198.51.100.2")  # a different visitor is unaffected
    clock.advance(timedelta(minutes=1))
    gw.analyze(req(), "198.51.100.1")


class CountingService(AnalyzeService):
    def __init__(self, *args: Any, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.runs = 0

    def analyze(self, request: AnalyzeRequest) -> Any:
        self.runs += 1
        return super().analyze(request)


def test_a_refused_request_does_not_run_the_analysis() -> None:
    clock = FakeClock()
    service = CountingService(MarketDataset([opportunity(id="TEST-FAKE-001")]), clock)
    gw = AnalyzeGateway(service, RateLimiter(limit=1, window=timedelta(minutes=1), clock=clock))
    gw.analyze(req(), "198.51.100.1")
    with pytest.raises(RateLimited):
        gw.analyze(req(), "198.51.100.1")
    assert service.runs == 1


def test_scenario_errors_pass_through_and_still_use_a_slot() -> None:
    clock = FakeClock()
    gw = gateway(clock, limit=1)
    bad = req(
        options=[
            {**req().options[0].model_dump(mode="json")},
            {
                **req().options[0].model_dump(mode="json"),
                "id": "alt",
                "is_original": False,
                "opportunity_id": "NOT-IN-DATASET",
            },
        ]
    )
    with pytest.raises(ScenarioError):
        gw.analyze(bad, "198.51.100.1")
    with pytest.raises(RateLimited):
        gw.analyze(req(), "198.51.100.1")


def test_logs_hold_outcomes_only_never_request_values_or_addresses(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    clock = FakeClock()
    gw = gateway(clock, limit=3)
    gw.analyze(req(), "198.51.100.77")
    covered = req().model_copy(update={"category": "high-protein breakfast"})
    gw.analyze(covered, "198.51.100.77")
    with pytest.raises(ScenarioError):
        gw.analyze(
            req(
                options=[
                    req().options[0].model_dump(mode="json"),
                    {
                        **req().options[0].model_dump(mode="json"),
                        "id": "alt",
                        "is_original": False,
                        "opportunity_id": "NOT-IN-DATASET",
                    },
                ]
            ),
            "198.51.100.77",
        )
    with pytest.raises(RateLimited):
        gw.analyze(req(), "198.51.100.77")

    lines = [r.getMessage() for r in caplog.records if r.name == "launchwise.analyze"]
    assert lines == [
        "analyze outcome=ok coverage=covered options=1",
        "analyze outcome=ok coverage=none options=1",
        "analyze outcome=invalid_scenario code=unknown_opportunity",
        "analyze outcome=rate_limited",
    ]
    for private in ("Secret Cakes", "198.51.100", "Pune", "home bakery", "NOT-IN-DATASET", NOIDA):
        assert private not in caplog.text
