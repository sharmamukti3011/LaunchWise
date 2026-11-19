from functools import cache
from pathlib import Path
from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.routes.analyze import RATE_LIMITED_DETAIL
from app.schemas.starter import StarterPageRequest
from app.services.rate_limit import RateLimited
from app.services.storefront_service import (
    DraftChanged,
    DraftNotFound,
    PreviewResult,
    PublishCapReached,
    PublishFailed,
    PublishResult,
    StorefrontService,
    UnpublishRefused,
)

router = APIRouter()

STYLESHEET = Path(__file__).resolve().parents[1] / "static" / "storefront.css"


def get_storefront_service(request: Request) -> StorefrontService:
    return cast(StorefrontService, request.app.state.storefront_service)


@router.post("/storefront/preview", response_model=PreviewResult)
def preview_page(
    payload: StarterPageRequest,
    request: Request,
    response: Response,
    service: Annotated[StorefrontService, Depends(get_storefront_service)],
) -> PreviewResult:
    """Build the page from the owner's text and request approval for it. Nothing is public yet."""
    response.headers["Cache-Control"] = "no-store"
    try:
        return service.preview(payload, _client(request))
    except RateLimited as exc:
        raise _limited(exc) from exc


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


class PublishBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    draft_id: str = Field(min_length=1, max_length=64)
    # The hash of the page the owner was shown: publishing only works for exactly that page.
    config_hash: str = Field(pattern=r"^[0-9a-f]{64}$")


class UnpublishBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str = Field(min_length=1, max_length=80)
    token: str = Field(min_length=1, max_length=128)


def _client(request: Request) -> str:
    return request.client.host if request.client else "unknown"


def _limited(exc: RateLimited) -> HTTPException:
    return HTTPException(
        status_code=429, detail=RATE_LIMITED_DETAIL, headers={"Retry-After": str(exc.retry_after)}
    )


@router.post("/storefront/publish", response_model=PublishResult)
def publish_page(
    payload: PublishBody,
    request: Request,
    response: Response,
    service: Annotated[StorefrontService, Depends(get_storefront_service)],
) -> PublishResult:
    """ "Approve and publish": grants the approvals and puts the previewed page live."""
    response.headers["Cache-Control"] = "no-store"  # the response carries the unpublish token
    try:
        return service.publish(payload.draft_id, payload.config_hash, _client(request))
    except RateLimited as exc:
        raise _limited(exc) from exc
    except DraftNotFound as exc:
        raise HTTPException(
            status_code=404, detail="That preview has expired. Please preview the page again."
        ) from exc
    except DraftChanged as exc:
        raise HTTPException(
            status_code=409, detail="The page changed since you previewed it. Preview it again."
        ) from exc
    except PublishCapReached as exc:
        raise HTTPException(
            status_code=503,
            detail="Too many example pages are live right now. Please try again later.",
        ) from exc
    except PublishFailed as exc:
        raise HTTPException(
            status_code=500, detail="Something went wrong publishing the page. Please try again."
        ) from exc


@router.post("/storefront/unpublish")
def unpublish_page(
    payload: UnpublishBody,
    request: Request,
    service: Annotated[StorefrontService, Depends(get_storefront_service)],
) -> dict[str, bool]:
    try:
        service.unpublish(payload.slug, payload.token, _client(request))
    except RateLimited as exc:
        raise _limited(exc) from exc
    except UnpublishRefused as exc:
        # The same answer for a wrong token, an unknown page, an ended page and the example page.
        raise HTTPException(status_code=404, detail="That unpublish link is not valid.") from exc
    return {"unpublished": True}
