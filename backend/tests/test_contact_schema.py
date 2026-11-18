"""ContactRequest: validation, control-character and header-injection rejection."""

from typing import Any

import pytest
from pydantic import ValidationError

from app.schemas.contact import ContactRequest


def payload(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "name": "Asha Patil",
        "email": "asha@example.com",
        "message": "Hello, I would like to order a cake for Saturday.",
    }
    data.update(overrides)
    return data


def build(**overrides: Any) -> ContactRequest:
    return ContactRequest.model_validate(payload(**overrides))


def test_valid_request_is_accepted_and_honeypot_defaults_to_empty() -> None:
    request = build()
    assert request.name == "Asha Patil"
    assert request.website == ""


def test_surrounding_whitespace_is_trimmed() -> None:
    request = build(
        name="  Asha  ", email=" asha@example.com ", message="  A message that is long enough.  "
    )
    assert (request.name, request.email) == ("Asha", "asha@example.com")
    assert request.message == "A message that is long enough."


@pytest.mark.parametrize("name", ["Asha Patil", "आशा पाटील", "O'Brien-Smith Jr."])
def test_ordinary_names_in_any_script_are_accepted(name: str) -> None:
    assert build(name=name).name == name


@pytest.mark.parametrize("name", ["", "   ", "x" * 101])
def test_name_length_is_enforced(name: str) -> None:
    with pytest.raises(ValidationError):
        build(name=name)


@pytest.mark.parametrize(
    "name",
    [
        "Asha\r\nBcc: evil@x.test",
        "Asha\nX-Header: 1",
        "Asha\rX",
        "Asha\x00",
        "Asha\u2028X",
        "Asha\u2029X",
        "Asha\tX",
        "Asha\x1bX",
    ],
)
def test_control_and_line_separator_characters_are_rejected_in_name(name: str) -> None:
    with pytest.raises(ValidationError):
        build(name=name)


@pytest.mark.parametrize(
    "email", ["visitor@example.com", "first.last+tag@sub.example.co.in", "o'brien@example.org"]
)
def test_ordinary_emails_are_accepted(email: str) -> None:
    assert build(email=email).email == email


@pytest.mark.parametrize(
    "email",
    [
        "plain",
        "a@b",
        "a b@c.com",
        "a@@b.com",
        "a@b..com",
        "a@.com",
        "a@b.com.",
        ".a@b.com",
        "a.@b.com",
        "a..b@c.com",
        "a@-b.com",
        "a@b-.com",
        "@b.com",
        "ünï@b.com",
        "a@b.com\r\nBcc: x@y.test",
        "a@b.com\nBcc:x@y.test",
        "a@b.com\x00",
        "a@b.com\u2028Bcc:x@y.test",
        "a@b.com, other@x.test",
        "a@b.com;other@x.test",
        "<a@b.com>",
        "a" * 250 + "@b.com",
    ],
)
def test_malformed_or_injecting_emails_are_rejected(email: str) -> None:
    with pytest.raises(ValidationError):
        build(email=email)


def test_a_trailing_line_separator_is_trimmed_not_kept() -> None:
    # Python treats U+2028 as whitespace, so it is stripped at the ends. What reaches the mail
    # code is clean; only a separator in the middle of a value is rejected (tests above).
    request = build(email="a@b.com\u2028", name="Asha\u2029")
    assert request.email == "a@b.com" and request.name == "Asha"


@pytest.mark.parametrize("message", ["", "         ", "x" * 2001])
def test_message_length_is_enforced_after_trimming(message: str) -> None:
    with pytest.raises(ValidationError):
        build(message=message)


def test_message_may_contain_newlines_and_tabs_and_crlf_is_normalised() -> None:
    request = build(message="Line one of the order.\r\nLine two:\twith a tab.\rLine three.")
    assert request.message == "Line one of the order.\nLine two:\twith a tab.\nLine three."


@pytest.mark.parametrize(
    "bad", ["Order\x00now please", "Order\x1bnow please", "Order\u2028now please"]
)
def test_message_rejects_other_control_characters(bad: str) -> None:
    with pytest.raises(ValidationError):
        build(message=bad)


@pytest.mark.parametrize("field", ["to", "cc", "bcc", "recipient", "from", "subject", "headers"])
def test_clients_cannot_supply_recipients_or_headers(field: str) -> None:
    with pytest.raises(ValidationError):
        build(**{field: "attacker@example.com"})


def test_a_filled_honeypot_is_still_a_valid_request() -> None:
    # The service decides what to do with it; rejecting here would tell bots they were caught.
    assert build(website="http://spam.example").website == "http://spam.example"


def test_message_bounds_are_one_to_two_thousand_characters() -> None:
    assert build(message="x").message == "x"
    assert build(message="x" * 2000).message == "x" * 2000


def test_field_bounds_match_the_form_contract() -> None:
    assert build(name="n" * 100).name == "n" * 100
    with pytest.raises(ValidationError):
        build(name="n" * 101)
    long_email = "a" * 64 + "@" + "b" * 63 + "." + "c" * 63 + "." + "d" * 57 + ".com"  # 254
    assert len(long_email) == 254 and build(email=long_email).email == long_email
    with pytest.raises(ValidationError):
        build(email="a" + long_email)  # 255
