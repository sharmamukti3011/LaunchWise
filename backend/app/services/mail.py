"""Outgoing mail. The sender is a protocol so the contact service never imports smtplib."""

import logging
import smtplib
import ssl
from collections.abc import Callable
from email.message import EmailMessage
from typing import Any, Literal, Protocol

from pydantic import SecretStr

from app.settings import Settings

logger = logging.getLogger("launchwise.mail")

DEFAULT_TIMEOUT_SECONDS = 10.0
Security = Literal["starttls", "ssl", "none"]


class ContactDeliveryError(Exception):
    """The message could not be delivered. Deliberately carries no server detail."""


class MailSender(Protocol):
    def send(self, message: EmailMessage) -> None:
        """Deliver the message or raise `ContactDeliveryError`."""
        ...


class SmtpMailSender:
    """Sends through an authenticated SMTP mailbox.

    The password lives in a `SecretStr` and is read in exactly one place, the `login` call. Failures
    are logged by class name and SMTP code only, never by message, because library and server
    messages are outside our control.
    """

    def __init__(
        self,
        *,
        host: str,
        port: int,
        security: Security,
        user: str,
        password: SecretStr,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        smtp_factory: Callable[..., Any] = smtplib.SMTP,
        smtp_ssl_factory: Callable[..., Any] = smtplib.SMTP_SSL,
    ) -> None:
        self._host = host
        self._port = port
        self._security = security
        self._user = user
        self._password = password
        self._timeout = timeout
        self._smtp_factory = smtp_factory
        self._smtp_ssl_factory = smtp_ssl_factory

    def send(self, message: EmailMessage) -> None:
        try:
            if self._security == "ssl":
                client = self._smtp_ssl_factory(
                    self._host,
                    self._port,
                    timeout=self._timeout,
                    context=ssl.create_default_context(),
                )
            else:
                client = self._smtp_factory(self._host, self._port, timeout=self._timeout)
            with client:
                if self._security == "starttls":
                    client.starttls(context=ssl.create_default_context())
                # Never authenticate over an unencrypted connection (only "none" skips this).
                if self._security != "none":
                    client.login(self._user, self._password.get_secret_value())
                client.send_message(message)
        except (smtplib.SMTPException, OSError) as exc:
            logger.warning(
                "smtp delivery failed: error=%s smtp_code=%s",
                type(exc).__name__,
                getattr(exc, "smtp_code", None),
            )
            raise ContactDeliveryError("could not deliver message") from None


class UnconfiguredMailSender:
    """Used when contact is enabled but the mailbox settings are incomplete (non-production
    only; production refuses to start). Fails closed instead of guessing."""

    def send(self, message: EmailMessage) -> None:
        logger.warning("smtp delivery failed: mailbox settings are incomplete")
        raise ContactDeliveryError("could not deliver message")


def mail_sender_from_settings(
    settings: Settings,
    *,
    smtp_factory: Callable[..., Any] = smtplib.SMTP,
    smtp_ssl_factory: Callable[..., Any] = smtplib.SMTP_SSL,
) -> MailSender:
    if not (
        settings.smtp_host and settings.smtp_port and settings.smtp_user and settings.smtp_password
    ):
        return UnconfiguredMailSender()
    return SmtpMailSender(
        host=settings.smtp_host,
        port=settings.smtp_port,
        security=settings.smtp_security,
        user=settings.smtp_user,
        password=settings.smtp_password,
        smtp_factory=smtp_factory,
        smtp_ssl_factory=smtp_ssl_factory,
    )
