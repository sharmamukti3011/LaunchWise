from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import health
from app.settings import Settings, get_settings


def create_app(settings: Settings | None = None) -> FastAPI:
    # Resolving settings here makes the app fail loudly at startup on bad config.
    settings = settings or get_settings()
    app = FastAPI(title="LaunchWise")
    app.dependency_overrides[get_settings] = lambda: settings

    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_allowed_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.include_router(health.router, prefix="/api")
    return app
