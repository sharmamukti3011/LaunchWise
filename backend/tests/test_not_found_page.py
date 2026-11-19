"""Unknown URLs get a real 404 page. Only "/" renders the app. /api/* and static files still work.

The static checks always run. The behavioural test runs the repo's real Caddyfile in a container
and is skipped, never failed, when Docker or a Caddy image is not available. It does not pull.
"""

import http.client
import re
import shutil
import socket
import ssl
import subprocess
import time
import uuid
from collections.abc import Iterator
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
CADDYFILE = ROOT / "frontend" / "Caddyfile"
PAGE = ROOT / "frontend" / "404.html"
IMAGES = ("caddy:2-alpine", "launchwise-caddy:latest")
DOCKER = shutil.which("docker") or "docker"


def caddy_directives() -> str:
    lines = CADDYFILE.read_text().splitlines()
    return "\n".join(ln for ln in lines if not ln.lstrip().startswith("#"))


# ---- the page ---------------------------------------------------------------------------------


def test_the_404_page_exists_and_says_what_was_asked_for() -> None:
    html = PAGE.read_text()
    assert "<title>Page not found" in html
    assert re.search(r"<h1[^>]*>\s*Page not found\s*</h1>", html)
    assert (
        "There's nothing at this address. You can test a business idea from the home page." in html
    )
    assert re.search(r'<a[^>]*href="/"[^>]*>\s*Go to LaunchWise home\s*</a>', html)


def test_the_page_has_a_small_decorative_inline_svg_above_the_heading() -> None:
    html = PAGE.read_text()
    svg = re.search(r"<svg\b[^>]*>.*?</svg>", html, re.S)
    assert svg is not None and svg.start() < html.index("<h1")
    opening = svg.group(0).split(">", 1)[0]
    assert 'aria-hidden="true"' in opening
    assert re.search(r"180", opening + html)  # about 180px wide
    body = svg.group(0)
    assert body.count("<circle") >= 3  # a few crumbs
    assert not re.search(r"<(img|image)\b|href=|url\(", body)  # no external files


def test_the_page_loads_nothing_but_the_sites_own_stylesheet() -> None:
    html = PAGE.read_text()
    assert "<script" not in html and "<img" not in html
    assert not re.search(r'(src|href)="https?://', html)
    assert 'rel="stylesheet" href="/src/index.css"' in html  # Vite swaps in the hashed file
    assert "style=" not in html  # the site's CSP forbids inline styles


def test_the_page_adapts_to_dark_mode_and_phone_width() -> None:
    html = PAGE.read_text()
    assert "dark:" in html and 'name="color-scheme" content="light dark"' in html
    assert 'name="viewport" content="width=device-width, initial-scale=1.0"' in html
    assert "min-h-dvh" in html and "max-w-full" in html


def test_the_page_has_the_normal_footer_and_is_not_indexed() -> None:
    html = PAGE.read_text()
    assert "Hosted on GoDaddy · Built with Claude" in html
    assert 'href="/#contact"' in html  # the contact section lives on the home page
    assert '<meta name="robots" content="noindex"' in html


def test_the_build_includes_the_page_and_the_image_copies_it() -> None:
    config = (ROOT / "frontend" / "vite.config.ts").read_text()
    assert "404.html" in config and "rollupOptions" in config
    dockerfile = (ROOT / "frontend" / "Dockerfile").read_text()
    assert re.search(r"^COPY\s+.*\bfrontend/404\.html\b", dockerfile, re.M)


# ---- the Caddyfile ----------------------------------------------------------------------------


def test_the_catch_all_no_longer_falls_back_to_index_html() -> None:
    caddy = caddy_directives()
    assert "try_files" not in caddy, "an SPA fallback makes every URL return 200"
    assert re.search(r"handle_errors\s*\{", caddy)
    assert "404.html" in caddy


def test_the_storefront_prefix_is_proxied_to_the_backend_which_answers_for_itself() -> None:
    block = re.search(r"handle\s+/s/\*\s*\{(.*?)\n\t\}", caddy_directives(), re.S)
    assert block, "expected a dedicated handle /s/* block"
    assert "reverse_proxy backend:8000" in block.group(1) and "error" not in block.group(1)


def test_only_error_404s_get_the_page_so_a_backend_outage_is_not_called_not_found() -> None:
    errors = re.search(r"handle_errors\s*\{(.*)\n\t\}", caddy_directives(), re.S)
    assert errors and "err.status_code" in errors.group(1) and "404" in errors.group(1)


# ---- the real Caddy ---------------------------------------------------------------------------


def docker_image() -> str | None:
    if shutil.which("docker") is None:
        return None
    for image in IMAGES:
        probe = subprocess.run(  # noqa: S603 - fixed docker command, fixed image names
            [DOCKER, "image", "inspect", image], capture_output=True, check=False, timeout=20
        )
        if probe.returncode == 0:
            return image
    return None


class Caddy:
    """The repo's Caddyfile running in a container, reached over loopback HTTPS."""

    def __init__(self, port: int) -> None:
        self.port = port

    def get(self, path: str, method: str = "GET") -> tuple[int, dict[str, str], str]:
        context = ssl.create_default_context()
        context.check_hostname = False
        context.verify_mode = ssl.CERT_NONE  # Caddy's own local CA: not trusted by the test
        raw = socket.create_connection(("127.0.0.1", self.port), timeout=10)
        wrapped = context.wrap_socket(raw, server_hostname="localhost")
        connection = http.client.HTTPSConnection("localhost", self.port, context=context)
        connection.sock = wrapped
        connection.request(method, path, headers={"Host": "localhost"})
        response = connection.getresponse()
        headers = {k.lower(): v for k, v in response.getheaders()}
        body = response.read().decode("utf-8", "replace")
        connection.close()
        return response.status, headers, body


@pytest.fixture(scope="module")
def caddy(tmp_path_factory: pytest.TempPathFactory) -> Iterator[Caddy]:
    image = docker_image()
    if image is None:
        pytest.skip("Docker and a local Caddy image are needed for this test")
    srv = tmp_path_factory.mktemp("srv")
    (srv / "assets").mkdir()
    (srv / "index.html").write_text("<!doctype html><title>home</title><div id=root></div>")
    (srv / "404.html").write_text(
        "<!doctype html><title>Page not found</title><h1>Page not found</h1>"
    )
    (srv / "assets" / "app.js").write_text("console.log('ok')")
    # Caddy runs as a non-root user in the container, so it must be able to read these.
    srv.chmod(0o755)
    (srv / "assets").chmod(0o755)
    for file in (srv / "index.html", srv / "404.html", srv / "assets" / "app.js"):
        file.chmod(0o644)
    name = f"lw-caddy-test-{uuid.uuid4().hex[:8]}"
    # Files are copied in, not bind-mounted: a mount of a temp path silently shows an empty
    # directory when Docker does not share that path with its VM.
    created = subprocess.run(  # noqa: S603 - fixed docker command, fixed image names
        [
            DOCKER, "create", "--name", name, "-p", "127.0.0.1::443",
            "-e", "SITE_DOMAIN=localhost", image,
        ],
        capture_output=True, text=True, check=False, timeout=60,
    )  # fmt: skip
    if created.returncode != 0:
        pytest.skip(f"could not create the Caddy container: {created.stderr.strip()[:120]}")
    try:
        copies = ((f"{srv}/.", f"{name}:/srv"), (str(CADDYFILE), f"{name}:/etc/caddy/Caddyfile"))
        for source, target in copies:
            subprocess.run([DOCKER, "cp", source, target], capture_output=True, check=True)  # noqa: S603
        subprocess.run([DOCKER, "start", name], capture_output=True, check=True)  # noqa: S603
        mapped = subprocess.run(  # noqa: S603
            [DOCKER, "port", name, "443/tcp"], capture_output=True, text=True, check=True
        ).stdout.split(":")[-1].strip()  # fmt: skip
        server = Caddy(int(mapped))
        deadline = time.monotonic() + 30
        while True:
            try:
                server.get("/")
                break
            except (OSError, ssl.SSLError, http.client.HTTPException):
                if time.monotonic() > deadline:
                    logs = subprocess.run(  # noqa: S603
                        [DOCKER, "logs", name], capture_output=True, text=True, check=False
                    )
                    pytest.fail(f"Caddy did not come up: {logs.stderr[-400:]}")
                time.sleep(0.5)
        yield server
    finally:
        subprocess.run([DOCKER, "rm", "-f", name], capture_output=True, check=False)  # noqa: S603


def test_only_the_home_page_renders_the_app(caddy: Caddy) -> None:
    status, _, body = caddy.get("/")
    assert status == 200 and "<title>home</title>" in body


@pytest.mark.parametrize(
    "path",
    [
        "/docs",
        "/docs/1",
        "/random",
        "/random/deeper/path",
        "/openapi.json",
        "/redoc",
        "/s",
        "/index",
    ],
)
def test_any_other_path_is_a_404_with_the_page_not_found_page(caddy: Caddy, path: str) -> None:
    status, headers, body = caddy.get(path)
    assert status == 404, path
    assert "Page not found" in body and "<title>home</title>" not in body
    assert headers["content-type"].startswith("text/html")


@pytest.mark.parametrize("path", ["/s/some-bakery", "/s/", "/s/a/b"])
def test_the_storefront_prefix_goes_to_the_backend_not_to_the_404_page(
    caddy: Caddy, path: str
) -> None:
    # No backend runs in this test, so the proxy fails (a 5xx). What matters is that Caddy no
    # longer answers these itself: the backend decides what a page address shows.
    status, _, body = caddy.get(path)
    assert status >= 500 and "Page not found" not in body


def test_the_error_page_is_not_itself_a_page_you_can_visit(caddy: Caddy) -> None:
    status, _, body = caddy.get("/404.html")
    assert status == 404 and "Page not found" in body


def test_real_static_files_still_work_and_a_missing_one_is_a_404(caddy: Caddy) -> None:
    status, _, body = caddy.get("/assets/app.js")
    assert status == 200 and "console.log" in body
    assert caddy.get("/assets/missing.js")[0] == 404


def test_api_paths_are_untouched_by_the_404_page(caddy: Caddy) -> None:
    # No backend runs in this test, so the proxy fails (a 5xx), which must never become a
    # "Page not found" page. A backend 404 is passed through as the backend sends it.
    status, _, body = caddy.get("/api/health")
    assert status >= 500 and "Page not found" not in body


def test_the_404_page_carries_the_same_security_headers(caddy: Caddy) -> None:
    _, headers, _ = caddy.get("/random")
    assert headers.get("x-content-type-options") == "nosniff"
    assert headers.get("x-frame-options") == "DENY"
    assert "default-src 'self'" in headers.get("content-security-policy", "")
    assert "strict-transport-security" in headers
    assert "server" not in headers


def test_head_requests_get_the_same_statuses(caddy: Caddy) -> None:
    assert caddy.get("/", "HEAD")[0] == 200
    assert caddy.get("/docs", "HEAD")[0] == 404
