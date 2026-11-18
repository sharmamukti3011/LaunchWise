from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.services.analyze_gateway import AnalyzeGateway
from app.services.analyze_models import AnalyzeRequest, AnalyzeResponse
from app.services.rate_limit import RateLimited

router = APIRouter()

RATE_LIMITED_DETAIL = "Too many requests. Please try again shortly."


def get_analyze_gateway(request: Request) -> AnalyzeGateway:
    return cast(AnalyzeGateway, request.app.state.analyze_gateway)


@router.post("/analyze", response_model=AnalyzeResponse)
def analyze(
    payload: AnalyzeRequest,
    request: Request,
    gateway: Annotated[AnalyzeGateway, Depends(get_analyze_gateway)],
) -> AnalyzeResponse:
    # Behind Caddy, uvicorn's proxy-headers support makes this the real visitor address.
    # An inconsistent scenario raises ScenarioError, which a registered handler turns into a 422.
    client = request.client.host if request.client else "unknown"
    try:
        return gateway.analyze(payload, client)
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail=RATE_LIMITED_DETAIL,
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
