"""The seeded guided-demo scenarios, shipped inside the app package (the tests/ folder is not in
the image). A manifest names each scenario and points at an `AnalyzeRequest` JSON file.

Everything here is simulated demo data: the inputs are made up for the walkthrough, and the
market entries they link to are unverified placeholders. Every response says so.
Loading validates the whole catalog, so a bad file stops the app at startup, not mid-demo.
"""

import json
from pathlib import Path
from typing import Annotated, Any, Literal

from pydantic import BaseModel, ConfigDict, StringConstraints, ValidationError

from app.services.analyze_models import AnalyzeRequest, AnalyzeResponse, Slug

DEMO_DIR = Path(__file__).resolve().parents[1] / "data" / "demo_scenarios"
MANIFEST_NAME = "manifest.json"
MAX_FILE_BYTES = 64 * 1024

SIMULATED_NOTICE = (
    "Simulated demo data: the inputs and prices are made up for this walkthrough, and the "
    "market entries are unverified placeholders, not real findings."
)

Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=200)]
FileName = Annotated[str, StringConstraints(pattern=r"^[A-Za-z0-9_-]{1,80}\.json$")]


class DemoCatalogError(Exception):
    """The demo catalog is missing, malformed, or holds an invalid scenario."""


class _ManifestEntry(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    id: Slug
    title: Line
    summary: Line
    file: FileName


class DemoScenarioSummary(BaseModel):
    """What the visitor sees in the list. The request itself is never exposed here."""

    model_config = ConfigDict(frozen=True)

    id: str
    title: str
    summary: str
    simulated: Literal[True] = True
    notice: str = SIMULATED_NOTICE


class DemoScenarioList(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenarios: list[DemoScenarioSummary]


class DemoRunResponse(BaseModel):
    model_config = ConfigDict(frozen=True)

    scenario: DemoScenarioSummary
    simulated: Literal[True] = True
    notice: str = SIMULATED_NOTICE
    analysis: AnalyzeResponse


class DemoCatalog:
    def __init__(self, scenarios: list[tuple[DemoScenarioSummary, AnalyzeRequest]]) -> None:
        self._order = [summary for summary, _ in scenarios]
        self._requests = {summary.id: request for summary, request in scenarios}

    def summaries(self) -> list[DemoScenarioSummary]:
        return list(self._order)

    def summary(self, scenario_id: str) -> DemoScenarioSummary | None:
        return next((s for s in self._order if s.id == scenario_id), None)

    def request(self, scenario_id: str) -> AnalyzeRequest | None:
        return self._requests.get(scenario_id)


def _read_json(path: Path) -> Any:
    try:
        if path.stat().st_size > MAX_FILE_BYTES:
            raise DemoCatalogError(f"{path.name} is too large")
        return json.loads(path.read_text(encoding="utf-8"))
    except OSError as exc:
        raise DemoCatalogError(f"cannot read {path.name}: {exc.strerror}") from exc
    except json.JSONDecodeError as exc:
        raise DemoCatalogError(f"{path.name} is not valid JSON") from exc


def load_demo_catalog(folder: Path = DEMO_DIR) -> DemoCatalog:
    """Load and fully validate the catalog, or raise `DemoCatalogError`."""
    manifest = _read_json(folder / MANIFEST_NAME)
    raw_entries = manifest.get("scenarios") if isinstance(manifest, dict) else None
    if not isinstance(raw_entries, list) or not raw_entries:
        raise DemoCatalogError('manifest must have a non-empty "scenarios" list')
    loaded: list[tuple[DemoScenarioSummary, AnalyzeRequest]] = []
    seen: set[str] = set()
    for position, raw in enumerate(raw_entries, 1):
        try:
            entry = _ManifestEntry.model_validate(raw)
        except ValidationError as exc:
            raise DemoCatalogError(f"manifest entry {position} is invalid") from exc
        if entry.id in seen:
            raise DemoCatalogError(f"duplicate scenario id {entry.id!r}")
        seen.add(entry.id)
        try:
            request = AnalyzeRequest.model_validate(_read_json(folder / entry.file))
        except ValidationError as exc:
            raise DemoCatalogError(f"{entry.file} is not a valid analyze request") from exc
        summary = DemoScenarioSummary(id=entry.id, title=entry.title, summary=entry.summary)
        loaded.append((summary, request))
    return DemoCatalog(loaded)
