"""Pre-submission gate for the market dataset. Run with `make check-dataset`.

Fails (exit 1) while any entry still has a `.invalid` source URL, a TODO marker, or the
`unverified_sample` status. These are the placeholders shipped with the code; a human must replace
each one with a real, cited, verified entry. This is deliberately not part of `make check`, which
must pass during development while the placeholders exist.

Exit codes: 0 clean, 1 leftovers found, 2 the file itself is invalid.
"""

import sys
from collections.abc import Sequence
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.services.market_data import DATASET_PATH, DatasetError, load_dataset  # noqa: E402
from app.services.strategy_models import Opportunity  # noqa: E402


def _texts(entry: Opportunity) -> list[str]:
    return [
        entry.title,
        entry.signal_summary,
        entry.evidence,
        entry.source_name,
        entry.label,
        entry.verified_by or "",
        *entry.required_skills,
        *entry.required_equipment,
    ]


def find_problems(opportunities: Sequence[Opportunity]) -> list[str]:
    """One line per entry that still has a placeholder marker, naming every reason."""
    problems = []
    for entry in opportunities:
        reasons = []
        host = (entry.source_url.host or "").casefold()
        if host == "invalid" or host.endswith(".invalid"):
            reasons.append("source URL is a .invalid placeholder")
        if entry.verification_status == "unverified_sample":
            reasons.append("status is unverified_sample")
        if any("todo" in text.casefold() for text in _texts(entry)):
            reasons.append("contains a TODO marker")
        if reasons:
            problems.append(f"{entry.id}: " + "; ".join(reasons))
    return problems


def main(argv: Sequence[str]) -> int:
    path = Path(argv[0]) if argv else DATASET_PATH
    try:
        dataset = load_dataset(path)
    except DatasetError as exc:
        print(f"dataset is invalid: {exc}", file=sys.stderr)
        return 2
    problems = find_problems(dataset.opportunities)
    if problems:
        print(f"dataset is NOT ready for submission ({len(problems)} entries need work):")
        for line in problems:
            print(f"  - {line}")
        return 1
    print(f"dataset is ready: {len(dataset.opportunities)} entries, none are placeholders")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
