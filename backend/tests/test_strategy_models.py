"""Opportunity and StrategyOption validation. Fixtures are obviously fake test data."""

from datetime import date
from decimal import Decimal
from typing import Any

import pytest
from pydantic import ValidationError

from app.engine.feasibility import Sourced
from app.services.strategy_models import Opportunity, StrategyOption

D = Decimal


def fake_opportunity(**overrides: Any) -> Opportunity:
    data: dict[str, Any] = {
        "id": "TEST-FAKE-001",
        "title": "Test fixture opportunity",
        "location": "Pune",
        "category": "bakery",
        "signal_summary": "Fake signal for tests.",
        "evidence": "Fake evidence for tests.",
        "source_name": "test_fixture",
        "source_url": "https://example.invalid/test-fixture",
        "event_date": date(2027, 1, 10),
        "retrieved_date": date(2026, 11, 1),
        "verification_status": "unverified_sample",
        "signal_strength": "medium",
        "required_skills": [],
        "required_equipment": [],
        "lead_time_days": 7,
        "label": "test_fixture",
    }
    data.update(overrides)
    return Opportunity(**data)


def test_dated_opportunity_is_valid() -> None:
    assert fake_opportunity().is_evergreen is False


def test_event_date_required_when_not_evergreen() -> None:
    with pytest.raises(ValidationError, match="event_date"):
        fake_opportunity(event_date=None)


def test_event_date_optional_when_evergreen() -> None:
    opp = fake_opportunity(event_date=None, is_evergreen=True)
    assert opp.event_date is None


def test_unverified_sample_needs_no_verifier() -> None:
    opp = fake_opportunity()
    assert opp.verified_by is None and opp.verified_on is None


def test_verified_status_requires_verifier() -> None:
    with pytest.raises(ValidationError, match="verified_by"):
        fake_opportunity(verification_status="verified")


def test_rejects_bad_signal_strength() -> None:
    with pytest.raises(ValidationError):
        fake_opportunity(signal_strength="huge")


def test_rejects_non_http_source_url() -> None:
    with pytest.raises(ValidationError):
        fake_opportunity(source_url="javascript:alert(1)")


def test_rejects_negative_lead_time() -> None:
    with pytest.raises(ValidationError):
        fake_opportunity(lead_time_days=-1)


def test_strategy_option_rejects_float_price() -> None:
    with pytest.raises(ValidationError):
        StrategyOption(
            id="opt",
            title="t",
            is_original=True,
            price=800.0,
            variable_cost_per_unit=D("350"),
            fixed_startup_costs=D("6000"),
            minutes_per_unit=Sourced[int](value=90, source="assumption"),
        )
