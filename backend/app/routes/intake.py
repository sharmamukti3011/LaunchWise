from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.routes.analyze import RATE_LIMITED_DETAIL
from app.schemas.intake import IntakeRequest
from app.services.intake_models import IntakeResponse
from app.services.intake_service import IntakeService
from app.services.rate_limit import RateLimited

router = APIRouter()

# Fixed on purpose: nothing about keys, models or configuration reaches a visitor.
NOT_AVAILABLE_DETAIL = "Describing your idea is not available right now."


def get_intake_service(request: Request) -> IntakeService:
    return cast(IntakeService, request.app.state.intake_service)


@router.post("/intake", response_model=IntakeResponse)
def draft_from_description(
    payload: IntakeRequest,
    request: Request,
    service: Annotated[IntakeService, Depends(get_intake_service)],
) -> IntakeResponse:
    """Draft the form from a description. It never runs the analysis."""
    client = request.client.host if request.client else "unknown"
    try:
        outcome = service.draft(payload.text, client)
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail=RATE_LIMITED_DETAIL,
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    if outcome.status == "not_configured":
        raise HTTPException(status_code=503, detail=NOT_AVAILABLE_DETAIL)
    return outcome.to_response()
