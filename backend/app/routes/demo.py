from typing import Annotated, cast

from fastapi import APIRouter, Depends, HTTPException, Path, Request

from app.routes.analyze import RATE_LIMITED_DETAIL
from app.services.analyze_models import Slug
from app.services.demo_catalog import DemoExplainResponse, DemoRunResponse, DemoScenarioList
from app.services.demo_service import DemoService, UnknownDemoScenario
from app.services.rate_limit import RateLimited

router = APIRouter(prefix="/demo")

UNKNOWN_DETAIL = "Unknown demo scenario."


def get_demo_service(request: Request) -> DemoService:
    return cast(DemoService, request.app.state.demo_service)


@router.get("/scenarios", response_model=DemoScenarioList)
def list_scenarios(service: Annotated[DemoService, Depends(get_demo_service)]) -> DemoScenarioList:
    return service.scenarios()


@router.post("/run/{scenario_id}", response_model=DemoRunResponse)
def run_scenario(
    scenario_id: Annotated[Slug, Path()],
    request: Request,
    service: Annotated[DemoService, Depends(get_demo_service)],
) -> DemoRunResponse:
    client = request.client.host if request.client else "unknown"
    try:
        return service.run(scenario_id, client)
    except (UnknownDemoScenario, RateLimited) as exc:
        raise _http_error(exc) from exc


@router.post("/explain/{scenario_id}", response_model=DemoExplainResponse)
def explain_scenario(
    scenario_id: Annotated[Slug, Path()],
    request: Request,
    service: Annotated[DemoService, Depends(get_demo_service)],
) -> DemoExplainResponse:
    client = request.client.host if request.client else "unknown"
    try:
        return service.explain(scenario_id, client)
    except (UnknownDemoScenario, RateLimited) as exc:
        raise _http_error(exc) from exc


def _http_error(exc: UnknownDemoScenario | RateLimited) -> HTTPException:
    if isinstance(exc, RateLimited):
        return HTTPException(
            status_code=429,
            detail=RATE_LIMITED_DETAIL,
            headers={"Retry-After": str(exc.retry_after)},
        )
    return HTTPException(status_code=404, detail=UNKNOWN_DETAIL)
