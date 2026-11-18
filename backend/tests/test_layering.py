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


APP_DIR = Path(__file__).resolve().parent.parent / "app"
CLAUDE_MODULES = [
    "orchestrator",
    "claude_client",
    "explanation_check",
    "explanation_facts",
    "explanation_template",
    "intake_models",
    "intake_check",
    "intake_service",
]


def test_only_the_adapter_imports_the_anthropic_sdk() -> None:
    for path in APP_DIR.rglob("*.py"):
        uses_sdk = any(m.split(".")[0] == "anthropic" for m in _imported_modules(path))
        assert uses_sdk == (path.name == "claude_client.py"), path.name


def test_the_orchestrator_has_no_network_or_database_imports() -> None:
    forbidden = {"anthropic", "httpx", "httpx2", "requests", "sqlite3", "smtplib", "socket"}
    for name in (*CLAUDE_MODULES[:1], *CLAUDE_MODULES[2:], "call_budget"):
        for module in _imported_modules(APP_DIR / "services" / f"{name}.py"):
            assert module.split(".")[0] not in forbidden, f"{name} imports {module}"


def test_the_engine_and_analyze_modules_never_import_the_claude_modules() -> None:
    files = list(ENGINE_DIR.rglob("*.py"))
    files += [APP_DIR / "services" / name for name in ANALYZE_MODULES]
    for path in files:
        for module in _imported_modules(path):
            assert module.rsplit(".", 1)[-1] not in CLAUDE_MODULES, f"{path.name}: {module}"


def test_no_claude_model_name_is_hard_coded_in_the_app() -> None:
    import re

    pattern = re.compile(r"claude-(opus|sonnet|haiku|fable|mythos)", re.IGNORECASE)
    for path in APP_DIR.rglob("*.py"):
        assert not pattern.search(path.read_text()), f"{path.name} hard-codes a model name"
