from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.health import HealthResponse
from app.services.health_service import HealthService
from app.settings import Settings, get_settings

router = APIRouter()


def get_health_service(settings: Annotated[Settings, Depends(get_settings)]) -> HealthService:
    return HealthService(settings)


@router.get("/health", response_model=HealthResponse)
def health(service: Annotated[HealthService, Depends(get_health_service)]) -> HealthResponse:
    return service.status()
