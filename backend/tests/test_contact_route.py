"""POST /api/contact end to end through the app, with fake mail and a fake clock."""

import logging
import smtplib
from datetime import timedelta
from typing import Any, cast

import pytest
from fastapi.testclient import TestClient
from uvicorn.middleware.proxy_headers import ProxyHeadersMiddleware

from app.main import create_app
from app.services.mail import ContactDeliveryError
from app.settings import Settings
from tests.fakes import FakeClock, FakeMailSender

URL = "/api/contact"
CADDY = "10.77.0.10"  # Caddy's fixed address in docker-compose.yml
GENERIC_DISABLED = {"detail": "The contact form is not available right now."}
NOT_CONFIGURED = {"detail": "The contact form is not configured yet."}
SENT_TEXT = "Thanks, your message has been sent."
SENTINEL = "ZQSENTINEL"


def good(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": "Asha Patil",
        "email": "asha@example.com",
        "message": "Hello, I would like to order a cake for Saturday.",
        "website": "",
    }
    data.update(overrides)
    return data


def settings(**overrides: Any) -> Settings:
    data: dict[str, Any] = {
        "app_env": "test",
        "contact_enabled": True,
        "contact_recipient": "owner@mail.test",
        "smtp_user": "mailbox@mail.test",
        # A complete mailbox, or the app would answer "not configured". Fake host: no test
        # can reach the network (see conftest), and the mail sender is always a fake.
        "smtp_host": "smtp.mail.test",
        "smtp_port": 465,
        "smtp_password": "s3cret-value-xyz",
    }
    data.update(overrides)
    return Settings(_env_file=None, **data)


def make_client(
    sender: FakeMailSender | None = None,
    clock: FakeClock | None = None,
    peer: tuple[str, int] = ("203.0.113.7", 50000),
    **setting_overrides: Any,
) -> TestClient:
    app = create_app(settings(**setting_overrides), mail_sender=sender, clock=clock)
    return TestClient(app, client=peer)


def via_proxy(app: Any, peer_host: str) -> TestClient:
    """Reach `app` from `peer_host`, wrapped the way uvicorn wraps it with --proxy-headers and
    FORWARDED_ALLOW_IPS=Caddy. Clients built from one app share its rate-limit state."""
    wrapped = ProxyHeadersMiddleware(cast(Any, app), trusted_hosts=CADDY)
    return TestClient(cast(Any, wrapped), client=(peer_host, 4321))


# ---- happy path and basic errors --------------------------------------------------------------


def test_valid_submission_returns_sent_and_delivers_one_message() -> None:
    sender = FakeMailSender()
    response = make_client(sender).post(URL, json=good())
    assert response.status_code == 200
    assert response.json() == {"status": "sent", "message": SENT_TEXT}
    [message] = sender.sent
    assert message["To"] == "owner@mail.test"
    assert message["From"] == "mailbox@mail.test"
    assert message["Reply-To"] == "asha@example.com"


def test_the_response_never_echoes_what_the_visitor_sent() -> None:
    body = make_client(FakeMailSender()).post(URL, json=good()).text
    assert "Asha" not in body and "cake" not in body and "asha@example.com" not in body


def test_honeypot_gets_the_same_success_response_and_nothing_is_sent() -> None:
    sender = FakeMailSender()
    real = make_client(sender).post(URL, json=good())
    trap = make_client(sender).post(URL, json=good(website="http://spam.example"))
    assert (trap.status_code, trap.json()) == (real.status_code, real.json())
    assert len(sender.sent) == 1  # only the real one


@pytest.mark.parametrize(
    "bad",
    [
        {"email": "not-an-email"},
        {"name": ""},
        {"message": ""},
        {"message": "x" * 2001},
        {"name": "Asha\r\nBcc: evil@x.test"},
        {"email": "a@b.com\r\nBcc: evil@x.test"},
        {"to": "attacker@example.com"},
        {"bcc": "attacker@example.com"},
    ],
)
def test_invalid_or_injecting_submissions_get_422_and_send_nothing(bad: dict[str, Any]) -> None:
    sender = FakeMailSender()
    response = make_client(sender).post(URL, json=good(**bad))
    assert response.status_code == 422
    assert sender.sent == []


def test_a_delivery_failure_returns_502_with_a_generic_body() -> None:
    sender = FakeMailSender(fail_with=ContactDeliveryError("smtp.secret-host.test refused"))
    response = make_client(sender).post(URL, json=good())
    assert response.status_code == 502
    assert set(response.json()) == {"detail"}
    assert "secret-host" not in response.text and "smtp" not in response.text.lower()


# ---- CONTACT_ENABLED=false --------------------------------------------------------------------


def test_disabled_returns_503_with_a_generic_body_and_never_touches_mail_or_smtp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def explode(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("SMTP must not be touched while the contact form is disabled")

    monkeypatch.setattr(smtplib, "SMTP", explode)
    monkeypatch.setattr(smtplib, "SMTP_SSL", explode)
    sender = FakeMailSender()
    # Even a fully configured mailbox must not be used while the flag is off.
    client = make_client(
        sender,
        contact_enabled=False,
        smtp_host="smtp.mail.test",
        smtp_port=587,
        smtp_password="s3cret",
    )
    response = client.post(URL, json=good())
    assert response.status_code == 503
    assert response.json() == GENERIC_DISABLED
    assert sender.sent == []


def test_disabled_answers_503_even_for_an_invalid_payload_and_leaks_nothing() -> None:
    client = make_client(FakeMailSender(), contact_enabled=False)
    for body in (good(email="nope"), good(to="x@y.test"), {}):
        response = client.post(URL, json=body)
        assert response.status_code == 503
        assert response.json() == GENERIC_DISABLED


def test_disabled_text_does_not_reveal_configuration() -> None:
    text = make_client(FakeMailSender(), contact_enabled=False).post(URL, json=good()).text.lower()
    for word in ("smtp", "env", "contact_enabled", "titan", "mailbox"):
        assert word not in text


def test_building_the_app_with_contact_disabled_creates_no_mail_sender(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(smtplib, "SMTP", lambda *a, **k: pytest.fail("SMTP constructed"))
    app = create_app(settings(contact_enabled=False))
    assert app.state.contact_service is None


# ---- rate limiting through the route ----------------------------------------------------------


def test_sixth_message_in_an_hour_from_one_client_is_429_with_retry_after() -> None:
    clock = FakeClock()
    client = make_client(FakeMailSender(), clock)
    for _ in range(5):
        assert client.post(URL, json=good()).status_code == 200
    response = client.post(URL, json=good())
    assert response.status_code == 429
    assert response.headers["retry-after"] == "3600"
    assert response.json() == {"detail": "Too many messages. Please try again later."}
    clock.advance(timedelta(minutes=59))
    assert client.post(URL, json=good()).status_code == 429
    assert client.post(URL, json=good()).headers["retry-after"] == "60"
    clock.advance(timedelta(minutes=1))
    assert client.post(URL, json=good()).status_code == 200


def test_the_limit_defaults_to_five_per_hour_and_is_tunable_from_settings() -> None:
    defaults = Settings(_env_file=None)
    assert (defaults.contact_rate_limit_per_ip, defaults.contact_rate_window_seconds) == (5, 3600)
    clock = FakeClock()
    tuned = make_client(
        FakeMailSender(), clock, contact_rate_limit_per_ip=2, contact_rate_window_seconds=60
    )
    assert [tuned.post(URL, json=good()).status_code for _ in range(3)] == [200, 200, 429]
    clock.advance(timedelta(seconds=60))
    assert tuned.post(URL, json=good()).status_code == 200


def test_the_contact_limit_uses_the_same_client_identification_as_analyze() -> None:
    # Both routes key on request.client.host, which uvicorn's proxy-headers support sets from
    # Caddy's X-Forwarded-For. Same app, same visitor address: separate limiters, same key.
    import inspect

    from app.routes import analyze, contact

    assert "request.client.host" in inspect.getsource(contact.submit_contact)
    assert "request.client.host" in inspect.getsource(analyze.analyze)


def test_limits_come_from_settings() -> None:
    client = make_client(FakeMailSender(), contact_rate_limit_per_ip=2)
    assert [client.post(URL, json=good()).status_code for _ in range(3)] == [200, 200, 429]


def test_distinct_client_addresses_have_independent_buckets() -> None:
    sender, clock = FakeMailSender(), FakeClock()
    app = create_app(settings(), mail_sender=sender, clock=clock)  # one app, shared limiter state
    first = TestClient(app, client=("198.51.100.1", 50000))
    second = TestClient(app, client=("198.51.100.2", 50000))
    assert [first.post(URL, json=good()).status_code for _ in range(6)] == [200] * 5 + [429]
    assert [second.post(URL, json=good()).status_code for _ in range(6)] == [200] * 5 + [429]
    assert len(sender.sent) == 10


def test_the_global_cap_applies_across_clients() -> None:
    sender, clock = FakeMailSender(), FakeClock()
    app = create_app(settings(contact_rate_limit_global=3), mail_sender=sender, clock=clock)
    statuses = [
        TestClient(app, client=(f"198.51.100.{i}", 50000)).post(URL, json=good()).status_code
        for i in range(5)
    ]
    assert statuses == [200, 200, 200, 429, 429]


def test_the_global_cap_defaults_to_200_per_hour() -> None:
    sender, clock = FakeMailSender(), FakeClock()
    app = create_app(settings(contact_rate_limit_per_ip=500), mail_sender=sender, clock=clock)
    client = TestClient(app, client=("198.51.100.1", 50000))
    assert [client.post(URL, json=good()).status_code for _ in range(201)] == [200] * 200 + [429]
    clock.advance(timedelta(hours=1))
    assert client.post(URL, json=good()).status_code == 200


# ---- proxy headers: trusted only from Caddy ---------------------------------------------------


def test_forwarded_for_from_caddy_gives_each_visitor_their_own_bucket() -> None:
    app = create_app(settings(), mail_sender=FakeMailSender(), clock=FakeClock())
    caddy = via_proxy(app, CADDY)
    visitor_a = {"X-Forwarded-For": "203.0.113.5"}
    visitor_b = {"X-Forwarded-For": "203.0.113.9"}
    statuses = [caddy.post(URL, json=good(), headers=visitor_a).status_code for _ in range(6)]
    assert statuses == [200] * 5 + [429]
    # Visitor B arrives through the same Caddy address but must not share A's bucket.
    assert caddy.post(URL, json=good(), headers=visitor_b).status_code == 200


def test_without_forwarded_for_everyone_behind_caddy_would_share_its_address() -> None:
    # Documents the failure mode the explicit FORWARDED_ALLOW_IPS setup exists to avoid.
    app = create_app(settings(), mail_sender=FakeMailSender(), clock=FakeClock())
    caddy = via_proxy(app, CADDY)
    assert [caddy.post(URL, json=good()).status_code for _ in range(6)] == [200] * 5 + [429]


def test_forwarded_for_from_anyone_but_caddy_is_ignored() -> None:
    sender = FakeMailSender()
    app = create_app(settings(), mail_sender=sender, clock=FakeClock())
    stranger = via_proxy(app, "198.51.100.66")  # not Caddy's address
    statuses = [
        stranger.post(URL, json=good(), headers={"X-Forwarded-For": f"203.0.113.{i}"}).status_code
        for i in range(6)
    ]
    # Forged, changing X-Forwarded-For values must not buy a fresh bucket each time.
    assert statuses == [200] * 5 + [429]
    assert len(sender.sent) == 5


def test_a_stranger_cannot_claim_another_visitors_exhausted_bucket_or_escape_their_own() -> None:
    app = create_app(settings(), mail_sender=FakeMailSender(), clock=FakeClock())
    caddy = via_proxy(app, CADDY)
    stranger = via_proxy(app, "198.51.100.66")
    for _ in range(5):
        assert (
            caddy.post(URL, json=good(), headers={"X-Forwarded-For": "203.0.113.5"}).status_code
            == 200
        )
    assert (
        caddy.post(URL, json=good(), headers={"X-Forwarded-For": "203.0.113.5"}).status_code == 429
    )
    # Same shared app: the stranger's forged claim is ignored, so they are judged by their own
    # address and are not blocked by visitor 203.0.113.5's exhausted bucket.
    assert (
        stranger.post(URL, json=good(), headers={"X-Forwarded-For": "203.0.113.5"}).status_code
        == 200
    )


# ---- CORS -------------------------------------------------------------------------------------


def test_cors_allows_only_the_configured_origin_for_post() -> None:
    client = make_client(FakeMailSender())
    allowed = client.post(URL, json=good(), headers={"Origin": "http://localhost:5173"})
    blocked = client.post(URL, json=good(), headers={"Origin": "https://evil.example"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in blocked.headers


# ---- not configured ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "missing", ["smtp_host", "smtp_port", "smtp_user", "smtp_password", "contact_recipient"]
)
def test_missing_mailbox_settings_give_a_fixed_not_configured_error_and_the_app_still_boots(
    missing: str,
) -> None:
    sender = FakeMailSender()
    app = create_app(settings(**{missing: None}), mail_sender=sender)  # boots, even in...
    client = TestClient(app, client=("203.0.113.7", 50000))
    response = client.post(URL, json=good())
    assert (response.status_code, response.json()) == (503, NOT_CONFIGURED)
    assert sender.sent == []
    assert client.get("/api/health").status_code == 200  # ...and the rest of the app works


def test_the_app_boots_in_production_with_contact_enabled_and_nothing_configured() -> None:
    app = create_app(Settings(_env_file=None, app_env="production", contact_enabled=True))
    client = TestClient(app)
    assert client.post(URL, json=good()).json() == NOT_CONFIGURED
    assert client.get("/api/health").status_code == 200


def test_with_nothing_set_at_all_the_answer_is_not_configured() -> None:
    client = TestClient(create_app(Settings(_env_file=None, app_env="test")))
    assert client.post(URL, json=good()).json() == NOT_CONFIGURED


def test_example_placeholders_count_as_not_configured() -> None:
    client = make_client(
        FakeMailSender(), smtp_host="smtp.example.invalid", smtp_password="changeme"
    )
    assert client.post(URL, json=good()).json() == NOT_CONFIGURED


def test_not_configured_answers_even_an_invalid_payload_and_reveals_nothing() -> None:
    client = make_client(FakeMailSender(), smtp_host=None)
    for body in (good(email="nope"), {}):
        response = client.post(URL, json=body)
        assert (response.status_code, response.json()) == (503, NOT_CONFIGURED)
    text = response.text.lower()
    for word in ("smtp", "password", "env", "titan", "mailbox", "smtp_host"):
        assert word not in text


def test_a_configured_but_disabled_form_says_it_is_not_available_not_unconfigured() -> None:
    client = make_client(FakeMailSender(), contact_enabled=False)
    assert client.post(URL, json=good()).json() == GENERIC_DISABLED


# ---- the real sender is built from settings, never from code ----------------------------------


def test_nothing_in_the_app_hard_codes_the_mail_host() -> None:
    from pathlib import Path

    root = Path(__file__).resolve().parents[1] / "app"
    for path in root.rglob("*.py"):
        text = path.read_text().lower()
        # The host comes from SMTP_HOST, never from code.
        assert "titan.email" not in text and "secureserver.net" not in text, path.name


def test_tests_cannot_open_a_network_connection() -> None:
    import smtplib

    with pytest.raises(RuntimeError, match="network"):
        smtplib.SMTP_SSL("smtpout.secureserver.net", 465, timeout=10)


# ---- logs and responses never carry visitor data ----------------------------------------------

CLIENT = "198.51.100.99"
FIELDS = ("name", "email", "message", "website")


def sentinel_body(field: str) -> dict[str, Any]:
    value = {
        "name": f"{SENTINEL} Name",
        "email": f"{SENTINEL.lower()}@example.com",
        "message": f"Please call about {SENTINEL}.",
        "website": f"http://{SENTINEL}.example",
    }[field]
    return good(**{field: value})


@pytest.mark.parametrize("field", FIELDS)
def test_a_sentinel_in_any_contact_field_never_reaches_a_log_or_a_response(
    field: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    sender = FakeMailSender()
    client = make_client(sender, peer=(CLIENT, 50000))
    body = sentinel_body(field)
    texts = [client.post(URL, json=body).text]  # sent, or honeypot for "website"
    # Validation failure with the sentinel inside an otherwise bad payload.
    texts.append(client.post(URL, json={**body, "email": f"{SENTINEL}-not-an-email"}).text)
    texts.append(client.post(URL, json={**body, "name": f"{SENTINEL}\r\nBcc: x@y.test"}).text)
    # Send failure whose own message contains the sentinel and the address.
    failing = FakeMailSender(fail_with=ContactDeliveryError(f"{SENTINEL} {CLIENT} smtp.host.test"))
    texts.append(make_client(failing, peer=(CLIENT, 50000)).post(URL, json=body).text)
    # Rate limited.
    limited = make_client(FakeMailSender(), peer=(CLIENT, 50000), contact_rate_limit_per_ip=1)
    limited.post(URL, json=body)
    texts.append(limited.post(URL, json=body).text)
    # Not configured and disabled.
    texts.append(make_client(FakeMailSender(), smtp_host=None).post(URL, json=body).text)
    texts.append(make_client(FakeMailSender(), contact_enabled=False).post(URL, json=body).text)

    for text in texts:
        assert SENTINEL.lower() not in text.lower() and CLIENT not in text
    assert SENTINEL.lower() not in caplog.text.lower()
    assert CLIENT not in caplog.text
    for private in ("Asha", "asha@example.com", "smtp.host.test", "s3cret-value-xyz"):
        assert private not in caplog.text


def test_contact_logs_are_the_four_outcomes_and_nothing_else(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG, logger="launchwise.contact")
    clock = FakeClock()
    ok = make_client(FakeMailSender(), clock, contact_rate_limit_per_ip=1)
    ok.post(URL, json=good())  # sent
    ok.post(URL, json=good())  # rate_limited
    make_client(FakeMailSender()).post(URL, json=good(website="x"))  # honeypot
    make_client(FakeMailSender(fail_with=ContactDeliveryError("x"))).post(URL, json=good())
    lines = [
        r.getMessage()
        for r in caplog.records
        if r.name == "launchwise.contact" and r.getMessage().startswith("contact outcome=")
    ]
    assert lines == [
        "contact outcome=sent",
        "contact outcome=rate_limited",
        "contact outcome=honeypot",
        "contact outcome=send_failed",
    ]


# ---- startup line -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("overrides", "needle"),
    [
        ({}, "Contact form: ready"),
        ({"contact_enabled": False}, "disabled (CONTACT_ENABLED is false)"),
        ({"smtp_host": None}, "not configured (SMTP_HOST is not set)"),
        ({"smtp_password": "changeme"}, "SMTP_PASSWORD is still the example placeholder"),
        ({"smtp_port": None}, "SMTP_PORT is not set"),
    ],
)
def test_startup_logs_whether_contact_is_ready_and_what_is_missing_never_values(
    overrides: dict[str, Any], needle: str, caplog: pytest.LogCaptureFixture
) -> None:
    with caplog.at_level(logging.INFO, logger="launchwise.contact"):
        create_app(settings(**overrides))
    [line] = [r.getMessage() for r in caplog.records if r.getMessage().startswith("Contact form:")]
    assert needle in line
    for value in ("s3cret-value-xyz", "mailbox@mail.test", "owner@mail.test", "smtp.mail.test"):
        assert value not in line
