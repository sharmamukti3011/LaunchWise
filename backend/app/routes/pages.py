"""The public side of starter pages: GET /s/<slug>. Nothing here changes anything."""

import re
from typing import Annotated, cast

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse

from app.services.storefront_render import render_unavailable
from app.services.storefront_service import StorefrontService

router = APIRouter()

SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{0,79}$")
# Every page, found or not, is kept out of search results and never cached, so a page that has
# been taken down stops being shown at once.
HEADERS = {"X-Robots-Tag": "noindex, nofollow", "Cache-Control": "no-store"}


def get_service(request: Request) -> StorefrontService:
    return cast(StorefrontService, request.app.state.storefront_service)


def _unavailable() -> HTMLResponse:
    return HTMLResponse(render_unavailable(), status_code=404, headers=HEADERS)


@router.get("/s/", include_in_schema=False)
def no_slug() -> HTMLResponse:
    return _unavailable()


@router.get("/s/{slug:path}", include_in_schema=False)
def show_page(
    slug: str, service: Annotated[StorefrontService, Depends(get_service)]
) -> HTMLResponse:
    html = service.page_html(slug) if SLUG.fullmatch(slug) else None
    if html is None:
        return _unavailable()
    return HTMLResponse(html, headers=HEADERS)
