from datetime import timedelta

from fastapi import FastAPI
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware

from app.api_errors import handle_scenario_error, handle_validation_error
from app.body_limit import BodySizeLimitMiddleware
from app.logging_config import configure_logging
from app.routes import analyze, contact, demo, health
from app.services.analyze_gateway import AnalyzeGateway
from app.services.analyze_service import AnalyzeService, ScenarioError
from app.services.clock import Clock, SystemClock
from app.services.contact_service import build_contact_service
from app.services.demo_catalog import load_demo_catalog
from app.services.demo_service import DemoService
from app.services.mail import MailSender, mail_sender_from_settings
from app.services.market_data import MarketDataset, load_dataset
from app.services.rate_limit import RateLimiter
from app.settings import Settings, get_settings

# Request body caps in bytes. Caddy enforces slightly lower caps in front of the app.
BODY_LIMITS = {"/api/analyze": 32 * 1024, "/api/contact": 16 * 1024}


def create_app(
    settings: Settings | None = None,
    mail_sender: MailSender | None = None,
    clock: Clock | None = None,
    dataset: MarketDataset | None = None,
) -> FastAPI:
    """Collaborators are injected so tests never touch real SMTP, real time or the real dataset."""
    # Resolving settings and the dataset here makes the app fail loudly at startup on bad config.
    settings = settings or get_settings()
    configure_logging()
    clock = clock or SystemClock()
    market = dataset or load_dataset()

    # Interactive docs and the OpenAPI schema describe every endpoint, so they are development-only.
    # docker-compose.yml forces APP_ENV=production on the server.
    docs = settings.app_env == "development"
    app = FastAPI(
        title="LaunchWise",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )
    app.dependency_overrides[get_settings] = lambda: settings

    # Added first so it sits inside CORS: even a 413 then carries the CORS headers.
    app.add_middleware(BodySizeLimitMiddleware, limits=BODY_LIMITS)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[settings.cors_allowed_origin],
        allow_methods=["GET", "POST"],
        allow_headers=["Content-Type"],
    )
    app.add_exception_handler(RequestValidationError, handle_validation_error)
    app.add_exception_handler(ScenarioError, handle_scenario_error)

    # One service per feature for the app's lifetime: the rate limiters hold state between
    # requests. While the contact form is disabled no mail sender is built, so SMTP is untouched.
    app.state.contact_service = None
    if settings.contact_enabled:
        app.state.contact_service = build_contact_service(
            settings, mail_sender or mail_sender_from_settings(settings), clock
        )
    gateway = AnalyzeGateway(
        AnalyzeService(market, clock),
        RateLimiter(
            limit=settings.analyze_rate_limit_per_ip,
            window=timedelta(seconds=settings.analyze_rate_window_seconds),
            clock=clock,
        ),
    )
    app.state.analyze_gateway = gateway
    # The demo reuses the analyze gateway, so it shares its rate limit and its outcome logging.
    # The catalog is validated here, so a bad scenario file stops the app at startup.
    app.state.demo_service = DemoService(load_demo_catalog(), gateway)

    app.include_router(health.router, prefix="/api")
    app.include_router(contact.router, prefix="/api")
    app.include_router(analyze.router, prefix="/api")
    app.include_router(demo.router, prefix="/api")
    return app
