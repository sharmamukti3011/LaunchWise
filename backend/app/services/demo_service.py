"""Runs a seeded demo scenario through the same analyze gateway as a visitor's own request."""

from app.services.analyze_gateway import AnalyzeGateway
from app.services.demo_catalog import (
    DemoCatalog,
    DemoRunResponse,
    DemoScenarioList,
)


class UnknownDemoScenario(Exception):
    """No demo scenario has that id."""


class DemoService:
    def __init__(self, catalog: DemoCatalog, gateway: AnalyzeGateway) -> None:
        self._catalog = catalog
        self._gateway = gateway

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
