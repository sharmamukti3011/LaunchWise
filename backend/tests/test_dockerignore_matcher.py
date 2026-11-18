"""The test matcher itself, plus what our real .dockerignore does and does not exclude."""

from pathlib import Path

import pytest

from tests.dockerignore import is_excluded, parse_dockerignore

ROOT = Path(__file__).resolve().parents[2]


def real_patterns() -> list[str]:
    return parse_dockerignore((ROOT / ".dockerignore").read_text())


def test_parse_skips_comments_and_blank_lines() -> None:
    assert parse_dockerignore("# c\n\n.env\n  docs  \n") == [".env", "docs"]


@pytest.mark.parametrize(
    ("path", "patterns", "expected"),
    [
        (".env", [".env"], True),
        (".env.production", [".env.*"], True),
        ("backend/.env", [".env"], False),  # no **/, so root only (Docker semantics)
        ("backend/tests/test_x.py", ["**/tests"], True),  # directory pattern covers children
        ("tests/test_x.py", ["**/tests"], True),  # ** matches zero directories
        ("docs/SPEC.md", ["docs"], True),
        ("backend/docs/x.md", ["docs"], False),
        ("a.db", ["*.db"], True),
        ("backend/data/a.db", ["*.db"], False),  # * never crosses a slash
        ("backend/data/a.db", ["**/*.db"], True),
        ("backend/app/main.py", ["**/tests", "docs"], False),
        ("backend/app/keep.txt", ["backend/app/*", "!backend/app/keep.txt"], False),
        ("backend/app/drop.txt", ["backend/app/*", "!backend/app/keep.txt"], True),
        ("x/y", ["?/y"], True),
        ("xx/y", ["?/y"], False),
    ],
)
def test_matcher_follows_docker_rules(path: str, patterns: list[str], expected: bool) -> None:
    assert is_excluded(path, patterns) is expected


@pytest.mark.parametrize(
    "path",
    [
        ".env",
        ".env.production",
        ".git/config",
        "backend/tests/test_x.py",
        "docs/SPEC.md",
        "frontend/node_modules/react/index.js",
        "frontend/dist/index.html",
        "backend/app/__pycache__/main.cpython-314.pyc",
        "backend/data/launchwise.db",  # a nested database must never reach an image
        "backend/data/launchwise.db-wal",
        "backend/app/service.log",
    ],
)
def test_the_real_dockerignore_keeps_these_out_of_the_build_context(path: str) -> None:
    assert is_excluded(path, real_patterns()), f"{path} would be copied into an image"


@pytest.mark.parametrize(
    "path",
    [
        "backend/app/main.py",
        "backend/app/data/market_opportunities.json",
        "backend/requirements.txt",
        "frontend/src/App.tsx",
        "frontend/Caddyfile",
        "frontend/package-lock.json",
    ],
)
def test_the_real_dockerignore_lets_these_into_the_build_context(path: str) -> None:
    assert not is_excluded(path, real_patterns()), f"{path} is wrongly excluded"
