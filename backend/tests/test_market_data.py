"""The market dataset loader: startup validation, coverage matching, and the shipped data file."""

import json
from pathlib import Path
from typing import Any

import pytest

from app.services.market_data import (
    DATASET_PATH,
    MAX_DATASET_BYTES,
    DatasetError,
    MarketDataset,
    load_dataset,
    normalise_place,
)
from app.services.strategy_models import Opportunity
from tests.pune_fixtures import opportunity

SENTINEL = "SENTINEL-EVIDENCE-TEXT"


def raw(**overrides: Any) -> dict[str, Any]:
    """One entry as it would appear in the JSON file."""
    return {**opportunity().model_dump(mode="json"), **overrides}


def write(tmp_path: Path, content: Any) -> Path:
    path = tmp_path / "dataset.json"
    path.write_text(content if isinstance(content, str) else json.dumps(content))
    return path


def dataset_file(tmp_path: Path, *entries: dict[str, Any]) -> Path:
    return write(tmp_path, {"opportunities": list(entries)})


# ---- the shipped file -------------------------------------------------------------------------


def test_the_shipped_dataset_loads_and_validates() -> None:
    dataset = load_dataset()
    assert len(dataset.opportunities) >= 1
    assert all(isinstance(o, Opportunity) for o in dataset.opportunities)
    assert len({o.id for o in dataset.opportunities}) == len(dataset.opportunities)


def test_the_shipped_dataset_lives_inside_the_backend_app_package() -> None:
    root = Path(__file__).resolve().parents[2]
    assert DATASET_PATH.relative_to(root).as_posix() == "backend/app/data/market_opportunities.json"


def test_the_shipped_dataset_is_the_five_cited_pune_entries() -> None:
    entries = load_dataset().opportunities
    assert [o.id for o in entries] == [f"PUNE-00{n}" for n in range(1, 6)]
    for entry in entries:
        assert entry.source_url.scheme == "https", entry.id
        assert not (entry.source_url.host or "").endswith(".invalid"), entry.id
        assert entry.source_name.strip(), entry.id


def test_every_shipped_entry_is_verified_by_the_owner_with_the_agreed_label() -> None:
    labels = {"PUNE-003": "Rental listing snapshot, checked 18 Nov 2026; listings change."}
    for entry in load_dataset().opportunities:
        assert entry.verification_status == "verified", entry.id
        assert entry.verified_by == "Mukti" and str(entry.verified_on) == "2026-11-18", entry.id
        expected = labels.get(entry.id, "Verified against the cited source on 18 Nov 2026.")
        assert entry.label == expected, entry.id
        assert "CHECK" not in entry.label and "TODO" not in entry.label.upper(), entry.id


def test_the_dated_festive_entry_is_dated_not_evergreen() -> None:
    entry = load_dataset().get("PUNE-002")
    assert entry is not None
    assert str(entry.event_date) == "2025-08-27" and entry.is_evergreen is False
    assert load_dataset().get("PUNE-003").is_evergreen is True  # type: ignore[union-attr]


def test_no_shipped_entry_claims_verification_without_a_verifier() -> None:
    # `verification_status` is set by a human after checking the source. Until then it must not
    # say "verified", and a verified entry must name who checked it and when.
    for entry in load_dataset().opportunities:
        if entry.verification_status == "verified":
            assert entry.verified_by and entry.verified_on, entry.id
        else:
            assert entry.verified_by is None and entry.verified_on is None, entry.id


def test_the_shipped_dataset_covers_pune_bakeries_only() -> None:
    dataset = load_dataset()
    assert all(normalise_place(o.location) == "pune" for o in dataset.opportunities)
    assert dataset.covers("Pune", "bakery")
    assert not dataset.covers("Noida", "high-protein breakfast")


# ---- loading and validation -------------------------------------------------------------------


def test_a_valid_file_loads(tmp_path: Path) -> None:
    dataset = load_dataset(dataset_file(tmp_path, raw(id="A"), raw(id="B")))
    assert [o.id for o in dataset.opportunities] == ["A", "B"]


def test_a_missing_file_is_a_clear_error(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="not found"):
        load_dataset(tmp_path / "nope.json")


@pytest.mark.parametrize(
    "content",
    ["not json", "[]", '"text"', "{}", '{"opportunities": "x"}', '{"opportunities": []}'],
)
def test_malformed_or_empty_files_are_rejected(tmp_path: Path, content: str) -> None:
    with pytest.raises(DatasetError):
        load_dataset(write(tmp_path, content))


def test_an_oversized_file_is_rejected_before_parsing(tmp_path: Path) -> None:
    path = write(tmp_path, " " * (MAX_DATASET_BYTES + 1))
    with pytest.raises(DatasetError, match="too large"):
        load_dataset(path)


def test_duplicate_ids_are_rejected(tmp_path: Path) -> None:
    with pytest.raises(DatasetError, match="duplicate"):
        load_dataset(dataset_file(tmp_path, raw(id="A"), raw(id="A")))


def test_a_verified_entry_needs_verified_by_and_verified_on(tmp_path: Path) -> None:
    bad = raw(id="A", verification_status="verified", verified_by=None, verified_on=None)
    with pytest.raises(DatasetError, match="verified_by"):
        load_dataset(dataset_file(tmp_path, bad))


def test_a_dated_entry_needs_a_date_unless_it_is_evergreen(tmp_path: Path) -> None:
    undated = raw(id="A", event_date=None, is_evergreen=False)
    with pytest.raises(DatasetError, match="event_date"):
        load_dataset(dataset_file(tmp_path, undated))
    evergreen = raw(id="B", event_date=None, is_evergreen=True)
    assert load_dataset(dataset_file(tmp_path, evergreen)).opportunities[0].is_evergreen


def test_unknown_keys_are_rejected_so_typos_cannot_silently_drop_a_rule(tmp_path: Path) -> None:
    typo = raw(id="A", verfied_by="someone")
    with pytest.raises(DatasetError, match="verfied_by"):
        load_dataset(dataset_file(tmp_path, typo))


def test_errors_name_the_entry_and_field_but_never_echo_its_content(tmp_path: Path) -> None:
    bad = raw(id="ENTRY-7", evidence=SENTINEL, signal_strength="enormous")
    with pytest.raises(DatasetError) as error:
        load_dataset(dataset_file(tmp_path, raw(id="OK"), bad))
    message = str(error.value)
    assert "entry 2" in message and "ENTRY-7" in message and "signal_strength" in message
    assert SENTINEL not in message and "enormous" not in message


# ---- coverage matching ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("Pune", "pune"),
        ("  pune  ", "pune"),
        ("PUNE", "pune"),
        ("Pune, Maharashtra", "pune"),
        ("Pune, Maharashtra, India", "pune"),
        ("Pune City", "pune"),
        ("pune district", "pune"),
        ("Pune Maharashtra", "pune"),
        ("Noida", "noida"),
        ("Noida, Uttar Pradesh", "noida"),
        ("Punekar Nagar", "punekar nagar"),
        ("", ""),
    ],
)
def test_places_are_normalised_tolerantly(text: str, expected: str) -> None:
    assert normalise_place(text) == expected


def make_dataset() -> MarketDataset:
    return MarketDataset([opportunity(id="P1"), opportunity(id="P2", category="bakery")])


@pytest.mark.parametrize(
    "location", ["Pune", " pune ", "PUNE", "Pune, Maharashtra", "Pune City", "Pune Maharashtra"]
)
def test_pune_variants_are_covered_for_bakeries(location: str) -> None:
    assert make_dataset().covers(location, "bakery")


@pytest.mark.parametrize("category", ["bakery", "Bakery", "home bakery", "  Home Bakery  "])
def test_bakery_category_variants_are_covered(category: str) -> None:
    assert make_dataset().covers("Pune", category)


@pytest.mark.parametrize(
    ("location", "category"),
    [
        ("Noida", "bakery"),
        ("Pune", "high-protein breakfast"),
        ("Noida", "high-protein breakfast"),
        ("Punekar Nagar", "bakery"),
        ("", "bakery"),
        ("Pune", ""),
    ],
)
def test_other_places_or_businesses_have_no_coverage(location: str, category: str) -> None:
    assert not make_dataset().covers(location, category)


def test_lookup_by_id_and_the_collection_is_read_only() -> None:
    dataset = make_dataset()
    assert dataset.get("P1") is not None and dataset.get("P1").id == "P1"  # type: ignore[union-attr]
    assert dataset.get("missing") is None
    assert isinstance(dataset.opportunities, tuple)
    assert dataset.ids() == frozenset({"P1", "P2"})


def test_duplicate_ids_cannot_be_built_in_memory_either() -> None:
    with pytest.raises(DatasetError, match="duplicate"):
        MarketDataset([opportunity(id="A"), opportunity(id="A")])
