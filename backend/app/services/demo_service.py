"""Runs a seeded demo scenario through the same analyze gateway as a visitor's own request."""

from app.services.analyze_gateway import AnalyzeGateway
from app.services.demo_catalog import (
    DemoCatalog,
    DemoExplainResponse,
    DemoRunResponse,
    DemoScenarioList,
)
from app.services.orchestrator import ExplainService


class UnknownDemoScenario(Exception):
    """No demo scenario has that id."""


class DemoService:
    def __init__(
        self, catalog: DemoCatalog, gateway: AnalyzeGateway, explainer: ExplainService
    ) -> None:
        self._catalog = catalog
        self._gateway = gateway
        self._explainer = explainer

    def scenarios(self) -> DemoScenarioList:
        return DemoScenarioList(scenarios=self._catalog.summaries())

    def run(self, scenario_id: str, client_key: str) -> DemoRunResponse:
        summary = self._catalog.summary(scenario_id)
        request = self._catalog.request(scenario_id)
        if summary is None or request is None:
            raise UnknownDemoScenario
        # Same gateway: same rate limit, same logging, same validation. The demo adds a label only.
        analysis = self._gateway.analyze(request, client_key)
        return DemoRunResponse(scenario=summary, analysis=analysis)

    def explain(self, scenario_id: str, client_key: str) -> DemoExplainResponse:
        """Explain a seeded scenario. The analysis is recomputed server-side, never client-supplied,
        so Claude can only ever explain the engine's own output."""
        request = self._catalog.request(scenario_id)
        if request is None:
            raise UnknownDemoScenario
        analysis = self._gateway.analyze(request, client_key)
        return DemoExplainResponse(
            scenario_id=scenario_id, explanation=self._explainer.explain(analysis, client_key)
        )
