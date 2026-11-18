from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Request

from app.schemas.contact import ContactRequest, ContactResponse
from app.services.contact_service import ContactService
from app.services.mail import ContactDeliveryError
from app.services.rate_limit import RateLimited

router = APIRouter()

# Generic on purpose: nothing about configuration, mailbox or the SMTP server reaches a visitor.
DISABLED_DETAIL = "The contact form is not available right now."
RATE_LIMITED_DETAIL = "Too many messages. Please try again later."
DELIVERY_FAILED_DETAIL = "We could not send your message. Please try again later."


def require_contact_service(request: Request) -> ContactService:
    """Resolved before the body is validated, so a disabled form answers 503 for any payload."""
    service = request.app.state.contact_service
    if service is None:
        raise HTTPException(status_code=503, detail=DISABLED_DETAIL)
    return cast(ContactService, service)


@router.post("/contact", response_model=ContactResponse)
def submit_contact(
    payload: ContactRequest,
    request: Request,
    service: Annotated[ContactService, Depends(require_contact_service)],
) -> ContactResponse:
    # Behind Caddy, uvicorn's proxy-headers support makes this the real visitor address.
    client = request.client.host if request.client else "unknown"
    try:
        service.submit(payload, client)
    except RateLimited as exc:
        raise HTTPException(
            status_code=429,
            detail=RATE_LIMITED_DETAIL,
            headers={"Retry-After": str(exc.retry_after)},
        ) from exc
    except ContactDeliveryError as exc:
        raise HTTPException(status_code=502, detail=DELIVERY_FAILED_DETAIL) from exc
    return ContactResponse(status="sent")
