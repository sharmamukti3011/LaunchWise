"""Explain the analysis of any valid request, not just a seeded demo scenario.

The visitor sends the same request they sent to /analyze. The analysis is recomputed here, so Claude
can only ever explain the engine's own output, never numbers a client supplied.
"""

from pydantic import BaseModel, ConfigDict

from app.services.analyze_gateway import AnalyzeGateway
from app.services.analyze_models import AnalyzeRequest
from app.services.orchestrator import ExplainService, Explanation


class AnalyzeExplainResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    explanation: Explanation


class AnalyzeExplainer:
    def __init__(self, gateway: AnalyzeGateway, explainer: ExplainService) -> None:
        self._gateway = gateway
        self._explainer = explainer

    def explain(self, request: AnalyzeRequest, client_key: str) -> AnalyzeExplainResponse:
        # Same gateway: the same rate limit, validation and outcome logging as /analyze.
        analysis = self._gateway.analyze(request, client_key)
        return AnalyzeExplainResponse(explanation=self._explainer.explain(analysis, client_key))
