"""`make check-dataset`: the pre-submission gate. Deliberately NOT part of `make check`."""

import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from app.services.market_data import load_dataset
from scripts.check_dataset import find_problems
from tests.pune_fixtures import opportunity

BACKEND = Path(__file__).resolve().parents[1]
ROOT = BACKEND.parent
SCRIPT = BACKEND / "scripts" / "check_dataset.py"


UNVERIFIED: dict[str, Any] = {
    "verification_status": "unverified_sample",
    "verified_by": None,
    "verified_on": None,
}


def clean(**overrides: Any) -> Any:
    data: dict[str, Any] = {
        "id": "PUNE-REAL-1",
        "source_name": "A real source",
        "source_url": "https://source.example.org/page",
        "evidence": "Checked by hand.",
        "label": "curated",
        "title": "Weekend stall",
        "signal_summary": "Steady footfall.",
    }
    data.update(overrides)
    return opportunity(**data)


def test_a_clean_entry_has_no_problems() -> None:
    assert find_problems([clean()]) == []


@pytest.mark.parametrize(
    ("overrides", "needle"),
    [
        ({"source_url": "https://example.invalid/x"}, ".invalid"),
        (UNVERIFIED, "unverified_sample"),
        ({"evidence": "TODO(verify): add a source"}, "TODO"),
        ({"title": "todo: rename"}, "TODO"),
        ({"signal_summary": "Fix this ToDo later"}, "TODO"),
        ({"source_name": "TODO"}, "TODO"),
        ({"label": "TODO(verify) placeholder"}, "TODO"),
        ({"required_skills": ["TODO"]}, "TODO"),
    ],
)  # fmt: skip
def test_each_kind_of_leftover_is_flagged_with_the_entry_id(
    overrides: dict[str, Any], needle: str
) -> None:
    [problem] = find_problems([clean(**overrides)])
    assert problem.startswith("PUNE-REAL-1:") and needle in problem


def test_one_entry_with_all_three_problems_reports_all_three() -> None:
    entry = clean(
        source_url="https://example.invalid/x",
        verification_status="unverified_sample",
        verified_by=None,
        verified_on=None,
        evidence="TODO(verify)",
    )
    [problem] = find_problems([entry])
    assert ".invalid" in problem and "unverified_sample" in problem and "TODO" in problem


def test_single_source_and_verified_entries_pass() -> None:
    entries = [
        clean(id="A", verification_status="single_source", verified_by=None, verified_on=None),
        clean(id="B"),
    ]
    assert find_problems(entries) == []


def test_the_shipped_dataset_fails_the_gate_until_a_human_verifies_every_entry() -> None:
    problems = find_problems(load_dataset().opportunities)
    assert len(problems) == len(load_dataset().opportunities)
    assert all("unverified_sample" in p for p in problems)
    assert any("CHECK" in p for p in problems)  # open questions in a label also block the gate


@pytest.mark.parametrize("field", ["label", "evidence", "signal_summary"])
def test_a_check_note_in_the_text_fails_the_gate(field: str) -> None:
    entry = clean(**{field: "CHECK: confirm this date"})
    assert "CHECK" in "".join(find_problems([entry]))


def run_script(*args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(  # noqa: S603 - fixed interpreter and our own script
        [sys.executable, str(SCRIPT), *args],
        cwd=BACKEND,
        capture_output=True,
        text=True,
        check=False,
    )


def test_the_script_exits_nonzero_on_the_shipped_data_and_lists_every_entry() -> None:
    result = run_script()
    assert result.returncode == 1
    for entry in load_dataset().opportunities:
        assert entry.id in result.stdout + result.stderr


def test_the_script_exits_zero_on_a_clean_dataset(tmp_path: Path) -> None:
    path = tmp_path / "ok.json"
    path.write_text(json.dumps({"opportunities": [clean().model_dump(mode="json")]}))
    result = run_script(str(path))
    assert result.returncode == 0
    assert "1 entries" in result.stdout


def test_the_script_exits_with_a_distinct_code_when_the_file_is_invalid(tmp_path: Path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not json")
    assert run_script(str(path)).returncode == 2


def test_make_has_the_target_and_make_check_does_not_run_it() -> None:
    makefile = (ROOT / "Makefile").read_text()
    assert re.search(r"^\.PHONY:.*\bcheck-dataset\b", makefile, re.M)
    recipe = re.search(r"^check-dataset:\n((?:\t.*\n?)+)", makefile, re.M)
    assert recipe and "scripts/check_dataset.py" in recipe.group(1)
    check = re.search(r"^check:\n((?:\t.*\n?)+)", makefile, re.M)
    assert check and "check-dataset" not in check.group(1)
    assert "check_dataset" not in check.group(1)
