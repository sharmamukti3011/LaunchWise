"""Generic error bodies. Nothing a visitor submitted ever appears in them.

FastAPI's default 422 echoes each rejected input value back. These handlers keep only the field
path and a fixed message. An unknown field is reported against its parent, without its name,
because that name came from the visitor too.
"""

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.services.analyze_service import ScenarioError

INVALID_REQUEST_DETAIL = "The request was not valid."
INVALID_SCENARIO_DETAIL = "The scenario could not be analysed."
BODY_TOO_LARGE_DETAIL = "The request body is too large."
MAX_ERRORS = 10


def _field(location: tuple[object, ...]) -> str:
    parts = [str(part) for part in location if part != "body"]
    return ".".join(parts) or "request"


def validation_errors(exc: RequestValidationError) -> list[dict[str, str]]:
    errors: list[dict[str, str]] = []
    for error in exc.errors()[:MAX_ERRORS]:
        location = tuple(error.get("loc", ()))
        kind = str(error.get("type", ""))
        if kind == "extra_forbidden":
            errors.append({"field": _field(location[:-1]), "message": "Unknown field."})
        elif kind.startswith("json_"):
            errors.append({"field": "request", "message": "The body is not valid JSON."})
        else:
            # `msg` is fixed library or rule text. The submitted `input` is never read.
            errors.append({"field": _field(location), "message": str(error.get("msg", ""))})
    return errors


def error_body(detail: str, errors: list[dict[str, str]]) -> dict[str, object]:
    return {"detail": detail, "errors": errors}


async def handle_validation_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, RequestValidationError)  # noqa: S101 - registered for this type only
    body = error_body(INVALID_REQUEST_DETAIL, validation_errors(exc))
    return JSONResponse(status_code=422, content=body)


async def handle_scenario_error(request: Request, exc: Exception) -> JSONResponse:
    assert isinstance(exc, ScenarioError)  # noqa: S101 - registered for this type only
    body = error_body(INVALID_SCENARIO_DETAIL, [{"field": exc.field, "message": exc.message}])
    return JSONResponse(status_code=422, content=body)
