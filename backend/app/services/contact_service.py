"""Contact form logic: rate limits, honeypot, message composition, delivery."""

import logging
from datetime import timedelta
from email.message import EmailMessage

from app.schemas.contact import ContactRequest
from app.services.clock import Clock
from app.services.mail import ContactDeliveryError, MailSender
from app.services.rate_limit import RateLimited, RateLimiter
from app.settings import Settings

# Outcomes only. Never the visitor's name, email, message or address, and never mailbox details.
logger = logging.getLogger("launchwise.contact")

OVERALL_KEY = "all-visitors"
# Only used when contact is enabled outside production without mailbox settings; production
# refuses to start in that state (see Settings).
UNCONFIGURED_ADDRESS = "unconfigured@localhost.invalid"


def build_contact_message(
    request: ContactRequest, *, from_address: str, recipient: str
) -> EmailMessage:
    """Compose the email. From and To are ours; the visitor only appears in Reply-To and the body.

    `EmailMessage` refuses CR/LF in header values, a second line of defence behind the schema.
    """
    message = EmailMessage()
    message["From"] = from_address
    message["To"] = recipient
    message["Reply-To"] = request.email
    message["Subject"] = f"LaunchWise contact: {request.name}"
    message.set_content(
        "New message from the LaunchWise contact form.\n\n"
        f"Name: {request.name}\n"
        f"Email: {request.email}\n\n"
        f"{request.message}\n"
    )
    return message


class ContactService:
    def __init__(
        self,
        *,
        sender: MailSender,
        recipient: str,
        from_address: str,
        per_client: RateLimiter,
        overall: RateLimiter,
    ) -> None:
        self._sender = sender
        self._recipient = recipient
        self._from_address = from_address
        self._per_client = per_client
        self._overall = overall

    def submit(self, request: ContactRequest, client_key: str) -> None:
        """Raises `RateLimited` or `ContactDeliveryError`. Honeypot hits return normally."""
        try:
            # Per client first, then overall: a visitor already blocked by their own limit must
            # not use up the shared cap that everyone else depends on.
            self._per_client.check(client_key)
            self._overall.check(OVERALL_KEY)
        except RateLimited:
            logger.info("contact outcome=rate_limited")
            raise
        if request.website:
            # A bot. Act as if it worked, so it learns nothing, and send nothing.
            logger.info("contact outcome=honeypot")
            return
        message = build_contact_message(
            request, from_address=self._from_address, recipient=self._recipient
        )
        try:
            self._sender.send(message)
        except ContactDeliveryError:
            logger.warning("contact outcome=delivery_failed")
            raise
        logger.info("contact outcome=sent")


def build_contact_service(settings: Settings, sender: MailSender, clock: Clock) -> ContactService:
    return ContactService(
        sender=sender,
        recipient=settings.contact_recipient or UNCONFIGURED_ADDRESS,
        from_address=settings.smtp_user or UNCONFIGURED_ADDRESS,
        per_client=RateLimiter(
            limit=settings.contact_rate_limit_per_ip,
            window=timedelta(seconds=settings.contact_rate_window_seconds),
            clock=clock,
        ),
        overall=RateLimiter(
            limit=settings.contact_rate_limit_global,
            window=timedelta(seconds=settings.contact_rate_window_global_seconds),
            clock=clock,
        ),
    )
