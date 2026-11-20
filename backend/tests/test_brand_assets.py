"""Favicon and logo files: right sizes, local only, linked from every page, and shipped."""

import json
import re
import struct
from pathlib import Path

import pytest

from app.services.storefront_render import ICON_LINKS, render_page, render_unavailable
from tests.test_storefront_render import config

ROOT = Path(__file__).resolve().parents[2]
PUBLIC = ROOT / "frontend" / "public"
PNG_SIZES = {
    "favicon-32.png": 32,
    "apple-touch-icon.png": 180,
    "icon-192.png": 192,
    "icon-512.png": 512,
}
LINK = re.compile(r"<link\b[^>]*>")


def png_size(path: Path) -> tuple[int, int]:
    data = path.read_bytes()
    assert data[:8] == b"\x89PNG\r\n\x1a\n", f"{path.name} is not a real PNG"
    return struct.unpack(">II", data[16:24])


@pytest.mark.parametrize(("name", "size"), PNG_SIZES.items())
def test_each_png_is_a_real_square_png_of_its_size(name: str, size: int) -> None:
    assert png_size(PUBLIC / name) == (size, size)


def test_the_ico_holds_16_32_and_48_pixel_images() -> None:
    data = (PUBLIC / "favicon.ico").read_bytes()
    reserved, kind, count = struct.unpack("<HHH", data[:6])
    assert (reserved, kind) == (0, 1)
    sizes = []
    for i in range(count):
        width, height, *_rest, length, offset = struct.unpack(
            "<BBBBHHII", data[6 + 16 * i : 22 + 16 * i]
        )
        assert width == height and offset + length <= len(data)
        sizes.append(width)
    assert sorted(sizes) == [16, 32, 48]


def test_the_source_logo_is_kept() -> None:
    assert (PUBLIC / "brand" / "launchwise-logo.png").is_file()


def test_the_manifest_is_valid_and_points_at_real_local_icons() -> None:
    manifest = json.loads((PUBLIC / "site.webmanifest").read_text())
    assert manifest["name"] == "LaunchWise" and manifest["start_url"] == "/"
    sizes = {icon["sizes"]: icon["src"] for icon in manifest["icons"]}
    assert set(sizes) == {"192x192", "512x512"}
    for icon in manifest["icons"]:
        assert icon["src"].startswith("/") and "//" not in icon["src"]
        assert (PUBLIC / icon["src"].lstrip("/")).is_file()


def hrefs(html: str) -> list[str]:
    return [m for tag in LINK.findall(html) for m in re.findall(r'href="([^"]+)"', tag)]


@pytest.mark.parametrize("page", ["index.html", "404.html"])
def test_the_static_pages_link_the_icons_with_local_paths(page: str) -> None:
    html = (ROOT / "frontend" / page).read_text()
    for expected in ("/favicon.ico", "/favicon-32.png", "/apple-touch-icon.png"):
        assert expected in hrefs(html), (page, expected)
    for href in hrefs(html):
        assert not re.match(r"[a-z]+:|//", href), f"{page} links off-site: {href}"
        if not href.startswith("/src/"):  # the 404 page's stylesheet is swapped by Vite
            assert (PUBLIC / href.lstrip("/")).is_file(), href


def test_the_app_page_links_the_manifest() -> None:
    assert "/site.webmanifest" in hrefs((ROOT / "frontend" / "index.html").read_text())


def test_starter_pages_and_the_not_available_page_link_the_icons() -> None:
    for html in (render_page(config()), render_unavailable()):
        for _, href in ICON_LINKS:
            assert href in hrefs(html)
        for href in hrefs(html):
            assert href.startswith("/")  # local only, so the site's policy still passes


def test_the_template_icon_links_point_at_files_that_ship() -> None:
    for _, href in ICON_LINKS:
        assert (PUBLIC / href.lstrip("/")).is_file()


def test_the_frontend_image_copies_the_public_folder_into_the_build() -> None:
    dockerfile = "\n".join(
        ln for ln in (ROOT / "frontend" / "Dockerfile").read_text().splitlines()
        if not ln.lstrip().startswith("#")
    )  # fmt: skip
    assert re.search(r"^COPY\s+(?:--\S+\s+)*frontend/public\s+\./public\s*$", dockerfile, re.M)
    ignore = (ROOT / ".dockerignore").read_text()
    assert "public" not in ignore and "brand" not in ignore
