"""POST /api/contact end to end through the app, with fake mail and a fake clock."""

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
    assert response.json() == {"status": "sent"}
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
        {"message": "short"},
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


def test_sixth_message_from_one_client_is_429_with_retry_after() -> None:
    clock = FakeClock()
    client = make_client(FakeMailSender(), clock)
    for _ in range(5):
        assert client.post(URL, json=good()).status_code == 200
    response = client.post(URL, json=good())
    assert response.status_code == 429
    assert response.headers["retry-after"] == "600"
    assert set(response.json()) == {"detail"}
    clock.advance(timedelta(seconds=240))
    assert client.post(URL, json=good()).status_code == 429
    assert client.post(URL, json=good()).headers["retry-after"] == "360"
    clock.advance(timedelta(seconds=360))
    assert client.post(URL, json=good()).status_code == 200


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
