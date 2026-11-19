"""Static checks on the deployment files. Plain text on purpose: no YAML dependency needed."""

import re
from pathlib import Path

import pytest

from app.services.market_data import DATASET_PATH
from tests.dockerignore import is_excluded, parse_dockerignore

ROOT = Path(__file__).resolve().parents[2]
DOCKERFILES = ["backend/Dockerfile", "frontend/Dockerfile"]


def read(relative: str) -> str:
    return (ROOT / relative).read_text()


def directives(relative: str) -> str:
    """The file without comment lines, so a comment can't satisfy or trip a check."""
    lines = (ROOT / relative).read_text().splitlines()
    return "\n".join(ln for ln in lines if not ln.lstrip().startswith("#"))


def service_blocks(compose: str) -> dict[str, str]:
    """Split the `services:` section into one text block per service."""
    blocks: dict[str, str] = {}
    current: str | None = None
    in_services = False
    for line in compose.splitlines():
        if re.match(r"^services:\s*$", line):
            in_services = True
            continue
        if in_services and re.match(r"^\S", line):
            in_services = False
        if not in_services:
            continue
        name = re.match(r"^  ([a-z][\w-]*):\s*$", line)
        if name:
            current = name.group(1)
            blocks[current] = ""
        elif current:
            blocks[current] += line + "\n"
    return blocks


def final_stage(dockerfile: str) -> list[str]:
    lines = [ln.strip() for ln in dockerfile.splitlines() if ln.strip() and ln[0] != "#"]
    last_from = max(i for i, ln in enumerate(lines) if ln.upper().startswith("FROM "))
    return lines[last_from:]


# ---- Dockerfiles ------------------------------------------------------------------------------


@pytest.mark.parametrize("path", DOCKERFILES)
def test_final_stage_runs_as_a_non_root_user_before_the_command(path: str) -> None:
    stage = final_stage(read(path))
    users = [i for i, ln in enumerate(stage) if ln.upper().startswith("USER ")]
    commands = [i for i, ln in enumerate(stage) if ln.split()[0].upper() in {"CMD", "ENTRYPOINT"}]
    assert users, f"{path} never sets USER"
    user = stage[users[-1]].split()[1].split(":")[0]
    assert user not in {"root", "0"}
    assert commands and users[-1] < commands[0], "USER must come before CMD"


@pytest.mark.parametrize("path", DOCKERFILES)
def test_dockerfiles_bake_in_no_secrets_and_never_copy_the_whole_tree(path: str) -> None:
    text = directives(path)
    assert not re.search(r"^\s*(ENV|ARG)\s+\w*(KEY|PASSWORD|SECRET|TOKEN)", text, re.M | re.I)
    assert not re.search(r"^\s*(COPY|ADD)\s+\.\s+\.", text, re.M), "copy named paths only"
    assert not re.search(r"^\s*(COPY|ADD)\b.*\.env", text, re.M), "never copy .env into an image"


def test_backend_image_copies_only_the_app_and_trusts_no_proxy_by_default() -> None:
    text = directives("backend/Dockerfile")
    assert re.search(r"^COPY\s+backend/app\b", text, re.M)
    assert "--proxy-headers" in text
    assert "--no-access-log" in text  # the access log would record every visitor's IP address
    assert "--forwarded-allow-ips" not in text  # compose sets FORWARDED_ALLOW_IPS explicitly
    assert "HEALTHCHECK" in text


def test_frontend_image_ends_in_caddy_serving_the_built_assets() -> None:
    stage = final_stage(read("frontend/Dockerfile"))
    assert stage[0].lower().startswith("from caddy:")
    assert any("/srv" in ln and ln.upper().startswith("COPY") for ln in stage)


# ---- .dockerignore ----------------------------------------------------------------------------


def test_dockerignore_keeps_secrets_git_and_tests_out_of_the_build_context() -> None:
    entries = {ln.strip() for ln in read(".dockerignore").splitlines()}
    assert {".env", ".env.*", ".git", "**/tests"} <= entries


# ---- docker-compose.yml -----------------------------------------------------------------------


def test_compose_has_exactly_backend_and_caddy() -> None:
    assert set(service_blocks(read("docker-compose.yml"))) == {"backend", "caddy"}


def test_backend_publishes_no_ports_and_loads_secrets_from_env_file() -> None:
    backend = service_blocks(read("docker-compose.yml"))["backend"]
    assert not re.search(r"^\s+ports:", backend, re.M)
    assert re.search(r"^\s+env_file:", backend, re.M)
    assert ".env" in backend


def test_caddy_publishes_only_80_and_443() -> None:
    caddy = service_blocks(read("docker-compose.yml"))["caddy"]
    published = re.findall(r'^\s+- "?(\d+:\d+)(?:/\w+)?"?\s*$', caddy, re.M)
    mappings = [p for p in published if p in {"80:80", "443:443"} or ":" in p]
    assert sorted(mappings) == ["443:443", "80:80"]


def test_backend_is_locked_down() -> None:
    backend = service_blocks(read("docker-compose.yml"))["backend"]
    assert re.search(r"^\s+read_only:\s*true", backend, re.M)
    assert re.search(r"cap_drop:\s*\n\s+- ALL", backend)
    assert "no-new-privileges" in backend


def test_proxy_headers_are_trusted_from_caddys_fixed_address_only() -> None:
    compose = read("docker-compose.yml")
    blocks = service_blocks(compose)
    trusted = re.search(r"FORWARDED_ALLOW_IPS:\s*\"?([\d.]+)\"?\s*$", blocks["backend"], re.M)
    assert trusted, "FORWARDED_ALLOW_IPS must be an explicit address, not '*'"
    caddy_ip = re.search(r"ipv4_address:\s*\"?([\d.]+)\"?", blocks["caddy"])
    assert caddy_ip and caddy_ip.group(1) == trusted.group(1)


def test_compose_never_mentions_secret_variables() -> None:
    compose = read("docker-compose.yml").upper()
    for name in ("SMTP_PASSWORD", "ANTHROPIC_API_KEY"):
        assert name not in compose


# ---- Caddyfile --------------------------------------------------------------------------------


def test_www_redirects_permanently_to_the_root_domain() -> None:
    caddy = read("frontend/Caddyfile")
    assert re.search(r"^www\.\{\$SITE_DOMAIN[^}]*\}\s*\{", caddy, re.M)
    assert re.search(r"redir\s+https://\{\$SITE_DOMAIN[^}]*\}\{uri\}\s+permanent", caddy)


def test_api_paths_go_to_the_backend_and_the_rest_is_served_as_static_files() -> None:
    caddy = read("frontend/Caddyfile")
    assert re.search(r"handle\s+/api/\*\s*\{[^}]*reverse_proxy\s+backend:8000", caddy)
    # No SPA fallback: unknown paths are 404s (see test_not_found_page.py).
    assert "file_server" in caddy and "try_files" not in directives("frontend/Caddyfile")


def test_hsts_is_short_lived_without_subdomains_or_preload() -> None:
    caddy = directives("frontend/Caddyfile")
    assert re.search(r'Strict-Transport-Security\s+"?max-age=300"?\s*$', caddy, re.M)
    assert not re.search(r"includeSubDomains|preload", caddy, re.I)


def test_contact_requests_are_size_capped_before_they_reach_the_backend() -> None:
    caddy = directives("frontend/Caddyfile")
    block = re.search(r"handle\s+/api/contact\s*\{(.*?)\n\t\}", caddy, re.S)
    assert block, "expected a dedicated handle /api/contact block"
    assert re.search(r"request_body\s*\{[^}]*max_size\s+16KB", block.group(1))
    assert "reverse_proxy backend:8000" in block.group(1)
    # It must come before the general /api/* handler, which would otherwise match first.
    assert caddy.index("handle /api/contact") < caddy.index("handle /api/*")


# ---- the market dataset must ship inside the backend image ------------------------------------


def test_the_dataset_is_in_the_build_context_and_not_excluded_by_dockerignore() -> None:
    relative = DATASET_PATH.relative_to(ROOT).as_posix()
    assert (ROOT / relative).is_file()
    assert not is_excluded(relative, parse_dockerignore(read(".dockerignore"))), (
        f"{relative} is excluded by .dockerignore, so the image would crash at startup"
    )


def test_a_copy_instruction_in_the_backend_dockerfile_includes_the_dataset() -> None:
    relative = DATASET_PATH.relative_to(ROOT).as_posix()
    sources = re.findall(
        r"^COPY\s+(?:--\S+\s+)*(\S+)\s+\S+\s*$", directives("backend/Dockerfile"), re.M
    )
    assert any(relative == s or relative.startswith(s.rstrip("/") + "/") for s in sources), (
        f"no COPY in backend/Dockerfile covers {relative}; COPY sources: {sources}"
    )


def test_analyze_requests_are_size_capped_before_they_reach_the_backend() -> None:
    caddy = directives("frontend/Caddyfile")
    block = re.search(r"handle\s+/api/analyze\s*\{(.*?)\n\t\}", caddy, re.S)
    assert block, "expected a dedicated handle /api/analyze block"
    assert re.search(r"request_body\s*\{[^}]*max_size\s+32KB", block.group(1))
    assert "reverse_proxy backend:8000" in block.group(1)
    assert caddy.index("handle /api/analyze") < caddy.index("handle /api/*")


def test_explaining_a_request_is_size_capped_in_front_of_the_backend_too() -> None:
    caddy = directives("frontend/Caddyfile")
    block = re.search(r"handle\s+/api/analyze/explain\s*\{(.*?)\n\t\}", caddy, re.S)
    assert block, "expected a dedicated handle /api/analyze/explain block"
    assert re.search(r"request_body\s*\{[^}]*max_size\s+32KB", block.group(1))
    assert "reverse_proxy backend:8000" in block.group(1)
    assert caddy.index("handle /api/analyze/explain") < caddy.index("handle /api/*")


def test_compose_forces_production_so_the_docs_are_off_on_the_server() -> None:
    backend = service_blocks(read("docker-compose.yml"))["backend"]
    assert re.search(r"^\s+APP_ENV:\s*production\s*$", backend, re.M)


def test_the_demo_scenarios_ship_in_the_image() -> None:
    from app.services.demo_catalog import DEMO_DIR

    relative = DEMO_DIR.relative_to(ROOT).as_posix()
    assert (ROOT / relative / "manifest.json").is_file()
    assert not is_excluded(relative + "/manifest.json", parse_dockerignore(read(".dockerignore")))
    sources = re.findall(
        r"^COPY\s+(?:--\S+\s+)*(\S+)\s+\S+\s*$", directives("backend/Dockerfile"), re.M
    )
    assert any(relative.startswith(s.rstrip("/") + "/") for s in sources), sources


def test_intake_requests_are_size_capped_in_front_of_the_backend() -> None:
    caddy = directives("frontend/Caddyfile")
    block = re.search(r"handle\s+/api/intake\s*\{(.*?)\n\t\}", caddy, re.S)
    assert block, "expected a dedicated handle /api/intake block"
    assert re.search(r"request_body\s*\{[^}]*max_size\s+8KB", block.group(1))
    assert "reverse_proxy backend:8000" in block.group(1)
    assert caddy.index("handle /api/intake") < caddy.index("handle /api/*")
