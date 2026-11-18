"""Rate limit and outcome logging around the analyze service. The analysis itself stays pure."""

import logging

from app.services.analyze_models import AnalyzeRequest, AnalyzeResponse
from app.services.analyze_service import AnalyzeService, ScenarioError
from app.services.rate_limit import RateLimited, RateLimiter

# Outcomes only. Never the request's values, and never the client's address.
logger = logging.getLogger("launchwise.analyze")


class AnalyzeGateway:
    def __init__(self, service: AnalyzeService, limiter: RateLimiter) -> None:
        self._service = service
        self._limiter = limiter

    def analyze(self, request: AnalyzeRequest, client_key: str) -> AnalyzeResponse:
        try:
            self._limiter.check(client_key)
        except RateLimited:
            logger.info("analyze outcome=rate_limited")
            raise
        try:
            response = self._service.analyze(request)
        except ScenarioError as exc:
            logger.info("analyze outcome=invalid_scenario code=%s", exc.code)
            raise
        logger.info(
            "analyze outcome=ok coverage=%s options=%d",
            response.market_coverage,
            len(response.options),
        )
        return response
