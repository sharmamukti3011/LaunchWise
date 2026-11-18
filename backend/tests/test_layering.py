"""Guards the pure core: engine/ must not import I/O, web, DB, or LLM libraries."""

import ast
from pathlib import Path

ENGINE_DIR = Path(__file__).resolve().parent.parent / "app" / "engine"
FORBIDDEN = {"fastapi", "sqlite3", "anthropic", "httpx", "requests", "smtplib", "app.services"}


def _imported_modules(path: Path) -> set[str]:
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text())):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            modules.add(node.module)
    return modules


def test_engine_has_no_forbidden_imports() -> None:
    for path in ENGINE_DIR.rglob("*.py"):
        for module in _imported_modules(path):
            assert module.split(".")[0] not in FORBIDDEN, f"{path.name} imports {module}"
            assert not module.startswith("app.services"), f"{path.name} imports {module}"


ROUTES_DIR = Path(__file__).resolve().parent.parent / "app" / "routes"
ROUTE_FORBIDDEN = {"smtplib", "sqlite3", "anthropic", "ssl"}


def test_route_handlers_do_not_talk_to_smtp_or_databases_directly() -> None:
    for path in ROUTES_DIR.rglob("*.py"):
        for module in _imported_modules(path):
            assert module.split(".")[0] not in ROUTE_FORBIDDEN, f"{path.name} imports {module}"


ANALYZE_MODULES = ["analyze_models.py", "analyze_service.py"]
ANALYZE_FORBIDDEN = {"anthropic", "sqlite3", "httpx", "requests", "smtplib", "socket", "fastapi"}


def test_the_analyze_service_makes_no_claude_calls_and_touches_no_database_or_network() -> None:
    services = Path(__file__).resolve().parent.parent / "app" / "services"
    for name in ANALYZE_MODULES:
        for module in _imported_modules(services / name):
            assert module.split(".")[0] not in ANALYZE_FORBIDDEN, f"{name} imports {module}"
