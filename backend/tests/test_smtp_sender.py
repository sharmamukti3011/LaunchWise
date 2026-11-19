"""SmtpMailSender against a fake SMTP: call order, TLS, credentials, and what gets logged."""

import logging
import smtplib
import ssl
from email.message import EmailMessage
from types import TracebackType
from typing import Any

import pytest
from pydantic import SecretStr

from app.services.mail import (
    ContactDeliveryError,
    SmtpMailSender,
    UnconfiguredMailSender,
    mail_sender_from_settings,
)
from app.settings import Settings

PASSWORD = "p4ss-w0rd-NEVER-LOG-ME"


class FakeSMTP:
    """Records the conversation. One instance per connection."""

    instances: list["FakeSMTP"] = []
    fail_on: dict[str, Exception] = {}

    def __init__(self, host: str, port: int, **kwargs: Any) -> None:
        self.calls: list[tuple[str, tuple[Any, ...], dict[str, Any]]] = [
            ("connect", (host, port), kwargs)
        ]
        FakeSMTP.instances.append(self)
        self._maybe_fail("connect")

    def _maybe_fail(self, step: str) -> None:
        if step in FakeSMTP.fail_on:
            raise FakeSMTP.fail_on[step]

    def starttls(self, **kwargs: Any) -> None:
        self.calls.append(("starttls", (), kwargs))
        self._maybe_fail("starttls")

    def login(self, user: str, password: str) -> None:
        self.calls.append(("login", (user, password), {}))
        self._maybe_fail("login")

    def send_message(self, message: EmailMessage) -> None:
        self.calls.append(("send_message", (message,), {}))
        self._maybe_fail("send_message")

    def __enter__(self) -> "FakeSMTP":
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        self.calls.append(("close", (), {}))

    @property
    def steps(self) -> list[str]:
        return [name for name, _, _ in self.calls]


class FakeSMTPSSL(FakeSMTP):
    pass


@pytest.fixture(autouse=True)
def reset_fake() -> None:
    FakeSMTP.instances = []
    FakeSMTP.fail_on = {}


def sender(security: str = "starttls", **kwargs: Any) -> SmtpMailSender:
    return SmtpMailSender(
        host="smtp.mail.test",
        port=587,
        security=security,  # type: ignore[arg-type]
        user="owner@mail.test",
        password=SecretStr(PASSWORD),
        smtp_factory=FakeSMTP,
        smtp_ssl_factory=FakeSMTPSSL,
        **kwargs,
    )


def message() -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = "owner@mail.test"
    msg.set_content("hello")
    return msg


def test_starttls_upgrades_then_logs_in_then_sends_then_closes() -> None:
    msg = message()
    sender("starttls").send(msg)
    [conn] = FakeSMTP.instances
    assert conn.steps == ["connect", "starttls", "login", "send_message", "close"]
    login_args = next(args for name, args, _ in conn.calls if name == "login")
    assert login_args == ("owner@mail.test", PASSWORD)
    assert conn.calls[3][1] == (msg,)


def test_starttls_verifies_the_server_certificate() -> None:
    sender("starttls").send(message())
    context = FakeSMTP.instances[0].calls[1][2]["context"]
    assert isinstance(context, ssl.SSLContext)
    assert context.verify_mode == ssl.CERT_REQUIRED and context.check_hostname


def test_ssl_mode_connects_over_tls_and_does_not_starttls() -> None:
    sender("ssl").send(message())
    [conn] = FakeSMTP.instances
    assert isinstance(conn, FakeSMTPSSL)
    assert conn.steps == ["connect", "login", "send_message", "close"]
    context = conn.calls[0][2]["context"]
    assert isinstance(context, ssl.SSLContext) and context.verify_mode == ssl.CERT_REQUIRED


def test_unencrypted_mode_never_sends_credentials() -> None:
    sender("none").send(message())
    [conn] = FakeSMTP.instances
    assert conn.steps == ["connect", "send_message", "close"]
    assert PASSWORD not in repr(conn.calls)


def test_a_connect_timeout_is_always_set() -> None:
    sender("starttls").send(message())
    assert FakeSMTP.instances[0].calls[0][2]["timeout"] == 10.0
    FakeSMTP.instances = []
    sender("starttls", timeout=3.5).send(message())
    assert FakeSMTP.instances[0].calls[0][2]["timeout"] == 3.5


def test_password_only_ever_reaches_login() -> None:
    sender("starttls").send(message())
    for name, args, kwargs in FakeSMTP.instances[0].calls:
        if name != "login":
            assert PASSWORD not in repr((args, kwargs))


def test_the_sender_does_not_leak_the_password_through_repr_or_str() -> None:
    s = sender()
    assert PASSWORD not in repr(s) and PASSWORD not in str(s)
    assert PASSWORD not in repr(vars(s))


@pytest.mark.parametrize(
    "failure",
    [
        smtplib.SMTPAuthenticationError(535, b"5.7.8 authentication failed"),
        smtplib.SMTPRecipientsRefused({"x@y.test": (550, b"no")}),
        smtplib.SMTPServerDisconnected("gone"),
        ConnectionRefusedError("refused"),
        TimeoutError("timed out"),
        ssl.SSLCertVerificationError("bad cert"),
    ],
)
@pytest.mark.parametrize("step", ["connect", "starttls", "login", "send_message"])
def test_any_smtp_or_network_failure_becomes_a_generic_delivery_error(
    failure: Exception, step: str
) -> None:
    FakeSMTP.fail_on[step] = failure
    with pytest.raises(ContactDeliveryError) as raised:
        sender("starttls").send(message())
    assert str(raised.value) == "could not deliver message"
    assert FakeSMTP.instances[-1].steps[-1] == "close" or step == "connect"


def test_failures_log_the_class_and_smtp_code_but_never_the_password(
    caplog: pytest.LogCaptureFixture,
) -> None:
    # A hostile server (or library) message that happens to contain the password.
    FakeSMTP.fail_on["login"] = smtplib.SMTPAuthenticationError(535, PASSWORD.encode())
    with caplog.at_level(logging.DEBUG), pytest.raises(ContactDeliveryError):
        sender("starttls").send(message())
    text = caplog.text
    assert PASSWORD not in text
    assert "SMTPAuthenticationError" in text and "535" in text


def test_failure_with_a_message_containing_the_password_is_not_logged(
    caplog: pytest.LogCaptureFixture,
) -> None:
    FakeSMTP.fail_on["send_message"] = smtplib.SMTPException(f"boom {PASSWORD}")
    with caplog.at_level(logging.DEBUG), pytest.raises(ContactDeliveryError):
        sender("starttls").send(message())
    assert PASSWORD not in caplog.text and "SMTPException" in caplog.text


def settings(**overrides: Any) -> Settings:
    data: dict[str, Any] = {
        "app_env": "test",
        "contact_enabled": True,
        "smtp_host": "smtp.mail.test",
        "smtp_port": 465,
        "smtp_security": "ssl",
        "smtp_user": "owner@mail.test",
        "smtp_password": PASSWORD,
        "contact_recipient": "owner@mail.test",
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


def test_sender_is_built_from_settings() -> None:
    built = mail_sender_from_settings(
        settings(), smtp_factory=FakeSMTP, smtp_ssl_factory=FakeSMTPSSL
    )
    assert isinstance(built, SmtpMailSender)
    built.send(message())
    assert isinstance(FakeSMTP.instances[0], FakeSMTPSSL)
    assert FakeSMTP.instances[0].calls[0][1] == ("smtp.mail.test", 465)


@pytest.mark.parametrize("missing", ["smtp_host", "smtp_port", "smtp_user", "smtp_password"])
def test_incomplete_settings_give_a_sender_that_fails_closed(missing: str) -> None:
    built = mail_sender_from_settings(settings(**{missing: None}))
    assert isinstance(built, UnconfiguredMailSender)
    with pytest.raises(ContactDeliveryError):
        built.send(message())


def test_a_godaddy_style_mailbox_uses_smtp_ssl_with_a_ten_second_timeout_from_settings() -> None:
    # Host and port come only from settings. SSL is the default, so no mode needs to be set.
    cfg = Settings(
        _env_file=None,
        app_env="test",
        smtp_host="smtpout.secureserver.net",
        smtp_port=465,
        smtp_user="box@mail.test",
        smtp_password=PASSWORD,
        contact_recipient="owner@mail.test",
    )
    assert cfg.smtp_security == "ssl"
    built = mail_sender_from_settings(cfg, smtp_factory=FakeSMTP, smtp_ssl_factory=FakeSMTPSSL)
    built.send(message())
    [conn] = FakeSMTP.instances
    assert isinstance(conn, FakeSMTPSSL)
    assert conn.calls[0][1] == ("smtpout.secureserver.net", 465)
    assert conn.calls[0][2]["timeout"] == 10.0
    assert [name for name, *_ in conn.calls] == ["connect", "login", "send_message", "close"]
    assert conn.calls[1][1] == ("box@mail.test", PASSWORD)
