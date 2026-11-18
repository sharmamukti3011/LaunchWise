"""ContactService: honeypot, per-client then global limits, message composition, logging."""

import logging
from datetime import timedelta
from typing import Any

import pytest

from app.schemas.contact import ContactRequest
from app.services.contact_service import ContactService, build_contact_message
from app.services.mail import ContactDeliveryError
from app.services.rate_limit import RateLimited, RateLimiter
from tests.fakes import FakeClock, FakeMailSender

RECIPIENT = "owner@mail.test"
FROM = "mailbox@mail.test"
SECOND = timedelta(seconds=1)


def request(**overrides: Any) -> ContactRequest:
    data: dict[str, Any] = {
        "name": "Asha Patil",
        "email": "asha@example.com",
        "message": "Hello, I would like to order a cake for Saturday.",
    }
    data.update(overrides)
    return ContactRequest.model_validate(data)


def make_service(
    clock: FakeClock,
    sender: FakeMailSender,
    per_ip: int = 5,
    overall: int = 200,
) -> ContactService:
    return ContactService(
        sender=sender,
        recipient=RECIPIENT,
        from_address=FROM,
        per_client=RateLimiter(limit=per_ip, window=timedelta(minutes=10), clock=clock),
        overall=RateLimiter(limit=overall, window=timedelta(hours=1), clock=clock),
    )


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def sender() -> FakeMailSender:
    return FakeMailSender()


# ---- message composition ----------------------------------------------------------------------


def test_message_goes_to_the_server_side_recipient_from_the_mailbox_with_reply_to_visitor() -> None:
    msg = build_contact_message(request(), from_address=FROM, recipient=RECIPIENT)
    assert msg["To"] == RECIPIENT
    assert msg["From"] == FROM
    assert msg["Reply-To"] == "asha@example.com"
    assert msg["Subject"] == "LaunchWise contact: Asha Patil"
    assert msg["Cc"] is None and msg["Bcc"] is None


def test_message_body_carries_the_visitors_details_as_plain_text() -> None:
    msg = build_contact_message(request(), from_address=FROM, recipient=RECIPIENT)
    body = msg.get_content()
    assert "Asha Patil" in body and "asha@example.com" in body
    assert "order a cake for Saturday" in body
    assert msg.get_content_type() == "text/plain"


def test_only_the_expected_headers_are_set() -> None:
    msg = build_contact_message(request(), from_address=FROM, recipient=RECIPIENT)
    assert {k.lower() for k in msg} <= {
        "to",
        "from",
        "reply-to",
        "subject",
        "content-type",
        "content-transfer-encoding",
        "mime-version",
    }


def test_a_body_that_looks_like_headers_stays_in_the_body() -> None:
    nasty = "Please call me.\r\nBcc: evil@x.test\r\nSubject: hijack\r\n\r\nthanks"
    msg = build_contact_message(request(message=nasty), from_address=FROM, recipient=RECIPIENT)
    assert msg["Bcc"] is None
    assert msg["Subject"] == "LaunchWise contact: Asha Patil"
    assert "Bcc: evil@x.test" in msg.get_content()  # harmless text inside the body


def test_second_layer_refuses_newlines_in_headers_even_if_validation_were_bypassed() -> None:
    # model_construct skips validation, standing in for a future bug in the schema.
    sneaky = ContactRequest.model_construct(
        name="Asha\r\nBcc: evil@x.test",
        email="asha@example.com",
        message="long enough message body",
        website="",
    )
    with pytest.raises(ValueError, match="linefeed|carriage"):
        build_contact_message(sneaky, from_address=FROM, recipient=RECIPIENT)
    sneaky_email = ContactRequest.model_construct(
        name="Asha",
        email="asha@example.com\r\nBcc: evil@x.test",
        message="long enough message body",
        website="",
    )
    with pytest.raises(ValueError, match="linefeed|carriage"):
        build_contact_message(sneaky_email, from_address=FROM, recipient=RECIPIENT)


def test_non_ascii_names_are_encoded_safely() -> None:
    msg = build_contact_message(request(name="आशा पाटील"), from_address=FROM, recipient=RECIPIENT)
    assert "\n" not in msg["Subject"].replace("\r", "")
    assert "आशा पाटील" in str(msg["Subject"])


# ---- submit: the normal path ------------------------------------------------------------------


def test_a_valid_submission_sends_exactly_one_message(
    clock: FakeClock, sender: FakeMailSender
) -> None:
    make_service(clock, sender).submit(request(), "203.0.113.5")
    assert len(sender.sent) == 1
    assert sender.sent[0]["To"] == RECIPIENT


def test_a_delivery_failure_propagates_and_still_uses_a_rate_limit_slot(clock: FakeClock) -> None:
    failing = FakeMailSender(fail_with=ContactDeliveryError("could not deliver message"))
    service = make_service(clock, failing, per_ip=2)
    for _ in range(2):
        with pytest.raises(ContactDeliveryError):
            service.submit(request(), "203.0.113.5")
    with pytest.raises(RateLimited):
        service.submit(request(), "203.0.113.5")


# ---- honeypot ---------------------------------------------------------------------------------


def test_a_filled_honeypot_sends_nothing_and_looks_like_success(
    clock: FakeClock, sender: FakeMailSender
) -> None:
    make_service(clock, sender).submit(request(website="http://spam.example"), "203.0.113.5")
    assert sender.sent == []


def test_honeypot_submissions_still_count_toward_the_limit(
    clock: FakeClock, sender: FakeMailSender
) -> None:
    service = make_service(clock, sender, per_ip=3)
    for _ in range(3):
        service.submit(request(website="x"), "203.0.113.5")
    with pytest.raises(RateLimited):
        service.submit(request(), "203.0.113.5")
    assert sender.sent == []


# ---- rate limits: per client first, then overall ----------------------------------------------


def test_each_client_address_has_its_own_bucket(clock: FakeClock, sender: FakeMailSender) -> None:
    service = make_service(clock, sender, per_ip=2)
    for _ in range(2):
        service.submit(request(), "198.51.100.1")
    with pytest.raises(RateLimited):
        service.submit(request(), "198.51.100.1")
    for address in ("198.51.100.2", "203.0.113.9", "10.77.0.10"):
        service.submit(request(), address)  # none of these are affected
    assert len(sender.sent) == 5


def test_the_overall_cap_is_shared_by_all_clients(clock: FakeClock, sender: FakeMailSender) -> None:
    service = make_service(clock, sender, per_ip=5, overall=3)
    for i in range(3):
        service.submit(request(), f"198.51.100.{i}")
    with pytest.raises(RateLimited):
        service.submit(request(), "198.51.100.200")
    assert len(sender.sent) == 3


def test_a_client_refused_by_its_own_limit_does_not_use_up_the_overall_cap(
    clock: FakeClock, sender: FakeMailSender
) -> None:
    # Order matters: per-client first. If the overall cap were checked first, one noisy visitor
    # hammering a blocked address would drain it for everyone.
    service = make_service(clock, sender, per_ip=1, overall=2)
    service.submit(request(), "198.51.100.1")  # overall: 1 of 2
    for _ in range(10):
        with pytest.raises(RateLimited):
            service.submit(request(), "198.51.100.1")  # refused by the per-client limit
    service.submit(request(), "198.51.100.2")  # overall: 2 of 2, still available
    with pytest.raises(RateLimited):
        service.submit(request(), "198.51.100.3")  # now the overall cap is really gone
    assert len(sender.sent) == 2


def test_limits_reset_as_the_windows_pass(clock: FakeClock, sender: FakeMailSender) -> None:
    service = make_service(clock, sender, per_ip=1)
    service.submit(request(), "198.51.100.1")
    with pytest.raises(RateLimited):
        service.submit(request(), "198.51.100.1")
    clock.advance(timedelta(minutes=10))
    service.submit(request(), "198.51.100.1")
    assert len(sender.sent) == 2


def test_the_overall_window_is_independent_of_the_per_client_window(
    clock: FakeClock, sender: FakeMailSender
) -> None:
    service = make_service(clock, sender, per_ip=5, overall=1)
    service.submit(request(), "198.51.100.1")
    clock.advance(timedelta(minutes=10))  # per-client window is over, the hourly one is not
    with pytest.raises(RateLimited):
        service.submit(request(), "198.51.100.2")
    clock.advance(timedelta(minutes=50))
    service.submit(request(), "198.51.100.2")


# ---- subject ----------------------------------------------------------------------------------


def test_the_subject_names_the_visitor() -> None:
    message = build_contact_message(request(), from_address=FROM, recipient=RECIPIENT)
    assert message["Subject"] == "LaunchWise contact: Asha Patil"


def test_a_very_long_name_is_truncated_to_a_safe_subject_length() -> None:
    message = build_contact_message(request(name="N" * 100), from_address=FROM, recipient=RECIPIENT)
    assert len(message["Subject"]) <= 100 and message["Subject"].startswith("LaunchWise contact: N")
    assert "\n" not in message["Subject"] and "\r" not in message["Subject"]


def test_the_visitors_address_is_only_ever_in_reply_to_never_in_from() -> None:
    message = build_contact_message(request(), from_address=FROM, recipient=RECIPIENT)
    assert message["From"] == FROM and "asha@example.com" not in message["From"]
    assert message["Reply-To"] == "asha@example.com"


# ---- logging ----------------------------------------------------------------------------------


def test_logs_outcomes_only_never_visitor_data_or_the_client_address(
    clock: FakeClock, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG, logger="launchwise.contact")
    ok = make_service(clock, FakeMailSender(), per_ip=1)
    ok.submit(request(), "198.51.100.77")
    with pytest.raises(RateLimited):
        ok.submit(request(), "198.51.100.77")
    ok.submit(request(website="x"), "198.51.100.78")
    failing = make_service(clock, FakeMailSender(fail_with=ContactDeliveryError("x")))
    with pytest.raises(ContactDeliveryError):
        failing.submit(request(), "198.51.100.79")

    outcomes = [r.getMessage() for r in caplog.records if r.name == "launchwise.contact"]
    assert outcomes == [
        "contact outcome=sent",
        "contact outcome=rate_limited",
        "contact outcome=honeypot",
        "contact outcome=send_failed",
    ]
    for private in ("Asha", "asha@example.com", "cake for Saturday", "198.51.100", RECIPIENT):
        assert private not in caplog.text
