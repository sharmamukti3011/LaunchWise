"""Guided-demo catalog: shipped in the app package, validated at load, labelled simulated."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.analyze_models import AnalyzeRequest
from app.services.demo_catalog import (
    DEMO_DIR,
    SIMULATED_NOTICE,
    DemoCatalog,
    DemoCatalogError,
    load_demo_catalog,
)

APP_DIR = Path(__file__).resolve().parents[1] / "app"


def test_the_scenarios_live_inside_the_app_package_so_they_ship_in_the_image() -> None:
    assert APP_DIR in DEMO_DIR.parents
    assert not (Path(__file__).parent / "scenarios").exists()  # one copy only


def test_the_shipped_catalog_lists_the_four_scenarios_lead_first() -> None:
    catalog = load_demo_catalog()
    assert [s.id for s in catalog.summaries()] == [
        "pune-pivot",
        "pune-keep-original",
        "pune-nothing-viable",
        "noida-feasibility-only",
    ]


def test_every_scenario_has_a_title_a_summary_and_a_valid_request() -> None:
    catalog = load_demo_catalog()
    for summary in catalog.summaries():
        assert summary.title and summary.summary
        assert isinstance(catalog.request(summary.id), AnalyzeRequest)


def test_every_summary_is_labelled_as_simulated_demo_data() -> None:
    for summary in load_demo_catalog().summaries():
        assert summary.simulated is True
        assert summary.notice == SIMULATED_NOTICE
    assert "simulated" in SIMULATED_NOTICE.lower()
    assert "verification status" in SIMULATED_NOTICE.lower()  # market evidence shows its own
    assert "placeholder" not in SIMULATED_NOTICE.lower()  # the market entries are real sources


def test_the_lead_scenario_is_the_pune_bakery_at_ten_thousand_rupees() -> None:
    request = load_demo_catalog().request("pune-pivot")
    assert request is not None
    assert request.profile.location == "Pune"
    assert str(request.profile.budget) == "10000"
    assert request.profile.units_per_day == 3 and request.profile.days_per_week == 2


def test_an_unknown_id_is_none() -> None:
    assert load_demo_catalog().request("nope") is None


# ---- loading fails loudly on a bad catalog ----------------------------------------------------


def write_catalog(
    folder: Path, entries: list[dict[str, Any]], files: dict[str, Any] | None = None
) -> Path:
    shipped = json.loads((DEMO_DIR / "a_alternative_beats_thin_margin_original.json").read_text())
    for name, body in (files or {"ok.json": shipped}).items():
        (folder / name).write_text(body if isinstance(body, str) else json.dumps(body))
    (folder / "manifest.json").write_text(json.dumps({"scenarios": entries}))
    return folder


def entry(**overrides: Any) -> dict[str, Any]:
    data = {"id": "one", "title": "One", "summary": "First.", "file": "ok.json"}
    data.update(overrides)
    return data


def test_a_well_formed_catalog_loads(tmp_path: Path) -> None:
    catalog = load_demo_catalog(write_catalog(tmp_path, [entry()]))
    assert isinstance(catalog, DemoCatalog)
    assert [s.id for s in catalog.summaries()] == ["one"]


@pytest.mark.parametrize(
    "entries",
    [
        [],  # nothing to demo
        [entry(file="missing.json")],
        [entry(), entry(title="Dup")],  # duplicate id
        [entry(id="Has Space")],
        [entry(title="")],
        [entry(extra="x")],
        [entry(file="../escape.json")],  # must stay inside the folder
        [entry(file="/etc/passwd")],
    ],
)
def test_a_bad_manifest_entry_fails_loudly(tmp_path: Path, entries: list[dict[str, Any]]) -> None:
    with pytest.raises(DemoCatalogError):
        load_demo_catalog(write_catalog(tmp_path, entries))


def test_an_invalid_request_file_fails_loudly(tmp_path: Path) -> None:
    folder = write_catalog(tmp_path, [entry()], {"ok.json": {"profile": {}}})
    with pytest.raises(DemoCatalogError):
        load_demo_catalog(folder)


def test_a_file_that_is_not_json_fails_loudly(tmp_path: Path) -> None:
    folder = write_catalog(tmp_path, [entry()], {"ok.json": "{not json"})
    with pytest.raises(DemoCatalogError):
        load_demo_catalog(folder)


def test_a_missing_manifest_fails_loudly(tmp_path: Path) -> None:
    with pytest.raises(DemoCatalogError):
        load_demo_catalog(tmp_path)
