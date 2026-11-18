"""Shared builders for the explanation tests: real engine output for the seeded scenarios."""

import json

from app.services.analyze_models import AnalyzeResponse
from app.services.analyze_service import AnalyzeService
from app.services.demo_catalog import load_demo_catalog
from app.services.market_data import load_dataset
from tests.fakes import FakeClock

IDS = ["pune-pivot", "pune-keep-original", "pune-nothing-viable", "noida-feasibility-only"]


def analysis_for(scenario_id: str = "pune-pivot") -> AnalyzeResponse:
    request = load_demo_catalog().request(scenario_id)
    assert request is not None
    return AnalyzeService(load_dataset(), FakeClock()).analyze(request)


def reply(summary: str) -> str:
    return json.dumps({"summary": summary})


# A valid explanation of the lead scenario: three sentences, only figures and IDs from the data.
GOOD = (
    "The engine recommends Custom celebration cakes, which scored 83.25 out of 100. "
    "Each cake leaves a margin of ₹900.00, or 64.29% of the price, and the up-front cost fits your "
    "budget of ₹10,000.00. "
    "Treat it as a guide: the market entry TODO-VERIFY-PUNE-001 is an unverified placeholder, "
    "and nothing here is a promise of profit."
)
