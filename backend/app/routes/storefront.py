from functools import cache
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.routes.analyze import RATE_LIMITED_DETAIL
from app.schemas.starter import StarterPageRequest
from app.services.rate_limit import RateLimited
from app.services.storefront_service import PreviewResult, StorefrontService

router = APIRouter()

STYLESHEET = Path(__file__).resolve().parents[1] / "static" / "storefront.css"


def get_storefront_service(request: Request) -> StorefrontService:
    return cast(StorefrontService, request.app.state.storefront_service)


@router.post("/storefront/preview", response_model=PreviewResult)
def preview_page(
    payload: StarterPageRequest,
    request: Request,
    service: Annotated[StorefrontService, Depends(get_storefront_service)],
) -> PreviewResult:
    """Build the page from the owner's text and request approval for it. Nothing is public yet."""
    client = request.client.host if request.client else "unknown"
    try:
        return service.preview(payload, client)
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail=RATE_LIMITED_DETAIL,
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc


@cache
def _stylesheet() -> str:
    return STYLESHEET.read_text(encoding="utf-8")


@router.get("/storefront/style.css")
def stylesheet() -> Response:
    """The one stylesheet every starter page uses (the site's policy forbids inline styles)."""
    return Response(
        content=_stylesheet(),
        media_type="text/css",
        headers={"Cache-Control": "public, max-age=3600"},
    )
