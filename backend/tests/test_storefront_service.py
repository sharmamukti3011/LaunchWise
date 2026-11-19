"""Starter-page preview: a draft bound to the exact config, an approval, and an audit trail."""

import json
import logging
import re
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.engine.approval_payload import hash_model
from app.engine.approval_rules import State
from app.main import create_app
from app.schemas.starter import StarterPageRequest, to_config
from app.services.approvals import APPROVE_STRATEGY, ApprovalService, ApprovalStatus
from app.services.rate_limit import RateLimited, RateLimiter
from app.services.storefront_render import render_page
from app.services.storefront_service import (
    DRAFT_TTL,
    MAX_DRAFTS,
    StorefrontService,
    make_slug,
)
from app.settings import Settings
from tests.fakes import FakeClock

SENTINEL = "ZQSENTINEL"
CLIENT = "198.51.100.66"
URL = "/api/storefront/preview"
SLUG = re.compile(r"^[a-z0-9][a-z0-9-]{2,40}$")


def body(**overrides: Any) -> dict[str, Any]:
    data: dict[str, Any] = {
        "business_name": "Aarti's Home Bakery",
        "description": "Fresh cakes, made to order.",
        "contact_email": "aarti@example.com",
        "offer_title": "Custom celebration cakes",
        "offer_price": "1200",
        "food_business": True,
    }
    data.update(overrides)
    return data


def request(**overrides: Any) -> StarterPageRequest:
    return StarterPageRequest.model_validate(body(**overrides))


class Ids:
    """Predictable ids and suffixes so tests can name them."""

    def __init__(self) -> None:
        self.n = 0

    def __call__(self) -> str:
        self.n += 1
        return f"id{self.n:04d}"


def make_service(
    clock: FakeClock | None = None, *, limit: int = 100, max_drafts: int = MAX_DRAFTS
) -> tuple[StorefrontService, ApprovalService, FakeClock]:
    clock = clock or FakeClock()
    ids = Ids()
    approvals = ApprovalService(clock, ttl=DRAFT_TTL, id_factory=ids)
    limiter = RateLimiter(limit=limit, window=timedelta(minutes=1), clock=clock)
    service = StorefrontService(
        approvals,
        clock,
        limiter,
        id_factory=ids,
        suffix_factory=lambda: "a1b2c3",
        max_drafts=max_drafts,
    )
    return service, approvals, clock


# ---- the preview ------------------------------------------------------------------------------


def test_a_preview_returns_the_page_exactly_as_it_would_be_published() -> None:
    service, _, _ = make_service()
    result = service.preview(request(), CLIENT)
    assert result.preview_html == render_page(to_config(request()))
    assert result.config_hash == hash_model(to_config(request()))
    assert result.public_path == f"/s/{result.slug}"


def test_the_slug_is_url_safe_readable_and_ends_in_a_random_part() -> None:
    service, _, _ = make_service()
    slug = service.preview(request(), CLIENT).slug
    assert slug == "aarti-s-home-bakery-a1b2c3" and SLUG.match(slug)


@pytest.mark.parametrize(
    ("brand", "expected"),
    [
        ("Aarti's Home Bakery", "aarti-s-home-bakery-x1"),
        ("  --Chai & Co.!  ", "chai-co-x1"),
        ("आरती की बेकरी", "page-x1"),  # nothing ASCII left, so a neutral word is used
        ("Café Déjà", "cafe-deja-x1"),
        ("A" * 60, "a" * 30 + "-x1"),
        ("../../etc/passwd", "etc-passwd-x1"),
        ("s/../admin", "s-admin-x1"),
    ],
)
def test_slugs_are_safe_whatever_the_name(brand: str, expected: str) -> None:
    assert make_slug(brand, "x1") == expected
    assert re.fullmatch(r"[a-z0-9][a-z0-9-]*", make_slug(brand, "x1"))


def test_two_pages_with_the_same_name_get_different_slugs() -> None:
    clock = FakeClock()
    approvals = ApprovalService(clock, ttl=DRAFT_TTL)
    limiter = RateLimiter(limit=10, window=timedelta(minutes=1), clock=clock)
    service = StorefrontService(approvals, clock, limiter)  # real random suffixes
    assert service.preview(request(), CLIENT).slug != service.preview(request(), CLIENT).slug


# ---- approval and audit -----------------------------------------------------------------------


def test_a_preview_starts_a_run_and_requests_approval_for_the_exact_config() -> None:
    service, approvals, _ = make_service()
    result = service.preview(request(), CLIENT)
    assert approvals.state_of(result.draft_id) == State.STRATEGY_PROPOSED
    approval = approvals.get_approval(service.approval_id_of(result.draft_id))
    assert approval.action == APPROVE_STRATEGY
    assert approval.status == ApprovalStatus.PENDING
    assert approval.payload_hash == result.config_hash == hash_model(to_config(request()))


def test_the_request_is_written_to_the_audit_log() -> None:
    service, approvals, _ = make_service()
    result = service.preview(request(), CLIENT)
    events = [(r.event, r.outcome) for r in approvals.audit.records if r.run_id == result.draft_id]
    assert events == [
        ("run_started", "ok"),
        ("transition", "ok"),
        ("approval_requested", "ok"),
    ]
    requested = approvals.audit.records[-1]
    assert requested.action == APPROVE_STRATEGY and requested.payload_hash == result.config_hash


def test_the_audit_log_holds_hashes_only_never_the_page_content_or_the_client() -> None:
    service, approvals, _ = make_service()
    service.preview(
        request(business_name=f"{SENTINEL} Cakes", contact_email="zq@example.com"), CLIENT
    )
    dump = json.dumps([r.model_dump(mode="json") for r in approvals.audit.records])
    for private in (SENTINEL, "zq@example.com", "Fresh cakes", "1200", CLIENT):
        assert private not in dump
    assert {r.actor for r in approvals.audit.records} == {"visitor"}


def test_an_approval_for_one_page_cannot_be_used_for_another() -> None:
    service, approvals, _ = make_service()
    first = service.preview(request(), CLIENT)
    second = service.preview(request(offer_price="1300"), CLIENT)
    assert first.config_hash != second.config_hash
    assert approvals.get_approval(service.approval_id_of(first.draft_id)).run_id == first.draft_id


# ---- drafts expire and are capped -------------------------------------------------------------


def test_a_draft_is_kept_for_thirty_minutes_then_forgotten() -> None:
    service, _, clock = make_service()
    result = service.preview(request(), CLIENT)
    assert service.has_draft(result.draft_id)
    clock.advance(DRAFT_TTL - timedelta(seconds=1))
    assert service.has_draft(result.draft_id)
    clock.advance(timedelta(seconds=2))
    assert not service.has_draft(result.draft_id)


def test_the_number_of_drafts_is_capped_and_the_oldest_go_first() -> None:
    service, _, clock = make_service(max_drafts=3)
    ids = []
    for _ in range(5):
        ids.append(service.preview(request(), CLIENT).draft_id)
        clock.advance(timedelta(seconds=1))
    assert [service.has_draft(i) for i in ids] == [False, False, True, True, True]


def test_the_default_cap_on_drafts_is_a_few_hundred() -> None:
    assert 100 <= MAX_DRAFTS <= 2000 and timedelta(minutes=30) == DRAFT_TTL


# ---- limits and logs --------------------------------------------------------------------------


def test_previews_are_rate_limited_per_client() -> None:
    service, _, _ = make_service(limit=2)
    service.preview(request(), CLIENT)
    service.preview(request(), CLIENT)
    with pytest.raises(RateLimited):
        service.preview(request(), CLIENT)
    service.preview(request(), "203.0.113.1")  # another visitor is unaffected


def test_only_outcomes_are_logged_never_content_or_the_client(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    service, _, _ = make_service(limit=1)
    service.preview(
        request(business_name=f"{SENTINEL} Cakes", contact_email="zq@example.com"), CLIENT
    )
    with pytest.raises(RateLimited):
        service.preview(request(), CLIENT)
    lines = [r.getMessage() for r in caplog.records if r.name == "launchwise.storefront"]
    assert lines == ["storefront outcome=preview_created", "storefront outcome=rate_limited"]
    for private in (SENTINEL, "zq@example.com", "Fresh cakes", CLIENT):
        assert private not in caplog.text


# ---- the endpoint -----------------------------------------------------------------------------


def make_client(**cfg: Any) -> TestClient:
    settings = Settings(_env_file=None, app_env="test", **cfg)
    return TestClient(create_app(settings), client=(CLIENT, 50000))


def test_the_endpoint_returns_a_draft_with_the_page_and_nothing_is_public_yet() -> None:
    response = make_client().post(URL, json=body())
    assert response.status_code == 200
    data = response.json()
    assert set(data) == {
        "draft_id", "slug", "public_path", "config_hash", "expires_in_minutes", "preview_html",
    }  # fmt: skip
    assert data["expires_in_minutes"] == 30
    assert "Example page made with LaunchWise" in data["preview_html"]
    assert make_client().get(data["public_path"]).status_code == 404  # not live, nor reserved


def test_a_phone_sized_description_and_a_full_name_render() -> None:
    response = make_client().post(URL, json=body(business_name="n" * 60, description="d" * 300))
    assert response.status_code == 200


@pytest.mark.parametrize(
    ("field", "value", "code"),
    [
        ("business_name", "Free porn", "not_allowed"),
        ("description", "casino night", "not_allowed"),
        ("offer_title", "buy guns", "not_allowed"),
        ("business_name", "<b>x</b>", "no_links_or_markup"),
        ("description", "see https://example.com", "no_links_or_markup"),
        ("offer_title", "mail me@example.com", "no_links_or_markup"),
    ],
)
def test_refused_text_gets_a_fixed_code_and_is_never_echoed(
    field: str, value: str, code: str
) -> None:
    response = make_client().post(URL, json=body(**{field: value}))
    assert response.status_code == 422
    data = response.json()
    assert data["detail"] == "The request was not valid."
    assert any(e["field"] == field and code in e["message"] for e in data["errors"])
    assert value not in response.text


@pytest.mark.parametrize("bad", [{"offer_price": "0"}, {"business_name": ""}, {"slug": "x"}, {}])
def test_other_invalid_requests_are_generic_422s(bad: dict[str, Any]) -> None:
    payload = bad if bad == {} else body(**bad)
    assert make_client().post(URL, json=payload).status_code == 422


def test_the_endpoint_is_rate_limited_with_retry_after() -> None:
    client = make_client(analyze_rate_limit_per_ip=2, analyze_rate_window_seconds=60)
    assert client.post(URL, json=body()).status_code == 200
    assert client.post(URL, json=body()).status_code == 200
    limited = client.post(URL, json=body())
    assert limited.status_code == 429 and limited.headers["Retry-After"]
    assert limited.json() == {"detail": "Too many requests. Please try again shortly."}


def test_the_body_is_capped_at_four_kilobytes() -> None:
    padded = json.dumps(body()).encode() + b" " * (4 * 1024)
    response = make_client().post(URL, content=padded, headers={"Content-Type": "application/json"})
    assert response.status_code == 413


def test_get_is_not_allowed_on_the_preview() -> None:
    assert make_client().get(URL).status_code == 405


@pytest.mark.parametrize("field", ["business_name", "description", "offer_title", "contact_email"])
def test_a_sentinel_in_any_field_never_reaches_a_log_or_an_error_response(
    field: str, caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    client = make_client()
    value = f"{SENTINEL.lower()}@example.com" if field == "contact_email" else f"{SENTINEL} cakes"
    ok = client.post(URL, json=body(**{field: value}))
    assert ok.status_code in (200, 422)
    bad = client.post(URL, json=body(**{field: f"<b>{SENTINEL}</b> porn"}))
    assert bad.status_code == 422 and SENTINEL not in bad.text
    assert SENTINEL.lower() not in caplog.text.lower() and CLIENT not in caplog.text


def test_the_page_content_is_escaped_in_the_preview_html() -> None:
    data = make_client().post(URL, json=body(business_name="Tom & Jerry's")).json()
    assert "Tom &amp; Jerry&#x27;s" in data["preview_html"]
    assert "Tom & Jerry" not in data["preview_html"]


# ---- the stylesheet ---------------------------------------------------------------------------


def test_the_stylesheet_is_served_as_css_and_is_cacheable() -> None:
    response = make_client().get("/api/storefront/style.css")
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/css")
    assert "max-age" in response.headers["cache-control"]
    assert "prefers-color-scheme" in response.text


def test_the_stylesheet_loads_nothing_from_anywhere_else() -> None:
    css = make_client().get("/api/storefront/style.css").text
    assert "url(" not in css and "@import" not in css and "http" not in css
