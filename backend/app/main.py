from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routes import contact, health
from app.services.clock import Clock, SystemClock
from app.services.contact_service import build_contact_service
from app.services.mail import MailSender, mail_sender_from_settings
from app.settings import Settings, get_settings


def create_app(
    settings: Settings | None = None,
    mail_sender: MailSender | None = None,
    clock: Clock | None = None,
) -> FastAPI:
    """`mail_sender` and `clock` are injected so tests never touch real SMTP or real time."""
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

    # One service for the app's lifetime: the rate limiters hold state between requests.
    # While the form is disabled no mail sender is built, so SMTP cannot be touched at all.
    app.state.contact_service = None
    if settings.contact_enabled:
        app.state.contact_service = build_contact_service(
            settings, mail_sender or mail_sender_from_settings(settings), clock or SystemClock()
        )

    app.include_router(health.router, prefix="/api")
    app.include_router(contact.router, prefix="/api")
    return app
