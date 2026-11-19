"""The public side: /s/<slug>, publish and unpublish over HTTP, and the seeded example page."""

import logging
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.page_store import EXAMPLE_SLUG, PAGE_LIFETIME
from app.settings import Settings
from tests.fakes import FakeClock

CLIENT = "198.51.100.66"
SENTINEL = "ZQSENTINEL"
PREVIEW = "/api/storefront/preview"
PUBLISH = "/api/storefront/publish"
UNPUBLISH = "/api/storefront/unpublish"
GONE = "This example page is not available. Example pages made with LaunchWise last 7 days."


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


def make(clock: FakeClock | None = None, **cfg: Any) -> TestClient:
    settings = Settings(_env_file=None, app_env="test", **cfg)
    return TestClient(create_app(settings, clock=clock or FakeClock()), client=(CLIENT, 50000))


def publish(client: TestClient, **overrides: Any) -> dict[str, Any]:
    preview = client.post(PREVIEW, json=body(**overrides)).json()
    response = client.post(
        PUBLISH, json={"draft_id": preview["draft_id"], "config_hash": preview["config_hash"]}
    )
    assert response.status_code == 200, response.text
    return {**preview, **response.json()}


# ---- publishing and viewing -------------------------------------------------------------------


def test_publish_returns_the_path_and_a_token_and_the_page_is_then_public() -> None:
    client = make()
    live = publish(client)
    assert set(live) >= {"slug", "public_path", "unpublish_token", "expires_in_days"}
    assert live["public_path"] == f"/s/{live['slug']}" and live["expires_in_days"] == 7
    page = client.get(live["public_path"])
    assert page.status_code == 200 and page.text == live["preview_html"]


def test_a_visitor_sees_the_banner_the_footer_and_noindex() -> None:
    client = make()
    page = client.get(publish(client)["public_path"])
    assert page.headers["content-type"].startswith("text/html")
    assert page.headers["x-robots-tag"] == "noindex, nofollow"
    assert page.headers["cache-control"] == "no-store"
    assert "Example page made with LaunchWise" in page.text
    assert 'name="robots" content="noindex, nofollow"' in page.text
    assert "Made with LaunchWise" in page.text


def test_a_page_not_yet_published_is_not_public() -> None:
    client = make()
    preview = client.post(PREVIEW, json=body()).json()
    assert client.get(preview["public_path"]).status_code == 404


def test_pages_expire_after_seven_days() -> None:
    clock = FakeClock()
    client = make(clock)
    live = publish(client)
    clock.advance(PAGE_LIFETIME - timedelta(seconds=1))
    assert client.get(live["public_path"]).status_code == 200
    clock.advance(timedelta(seconds=1))
    assert client.get(live["public_path"]).status_code == 404


@pytest.mark.parametrize(
    "path", ["/s/nope", "/s/UPPER", "/s/a%2Fb", "/s/" + "a" * 200, "/s/x y", "/s/"]
)
def test_unknown_or_malformed_slugs_get_the_same_fixed_404(path: str) -> None:
    response = make().get(path)
    assert response.status_code == 404
    assert response.headers["x-robots-tag"] == "noindex, nofollow"
    assert GONE in response.text
    assert path.rsplit("/", 1)[-1] not in response.text or path.endswith("/")  # never echoed


def test_only_get_is_allowed_on_a_page() -> None:
    client = make()
    live = publish(client)
    assert client.post(live["public_path"]).status_code == 405
    assert client.delete(live["public_path"]).status_code == 405


# ---- refusals ---------------------------------------------------------------------------------


def test_an_unknown_draft_is_a_fixed_404() -> None:
    response = make().post(PUBLISH, json={"draft_id": "nope", "config_hash": "0" * 64})
    assert response.status_code == 404
    assert response.json() == {"detail": "That preview has expired. Please preview the page again."}


def test_a_changed_page_is_a_409_and_nothing_goes_live() -> None:
    client = make()
    preview = client.post(PREVIEW, json=body()).json()
    response = client.post(PUBLISH, json={"draft_id": preview["draft_id"], "config_hash": "0" * 64})
    assert response.status_code == 409
    assert response.json() == {
        "detail": "The page changed since you previewed it. Preview it again."
    }
    assert client.get(preview["public_path"]).status_code == 404


def test_the_cap_on_live_pages_is_a_fixed_503() -> None:
    client = make(max_live_pages=1)
    publish(client)
    preview = client.post(PREVIEW, json=body()).json()
    response = client.post(
        PUBLISH, json={"draft_id": preview["draft_id"], "config_hash": preview["config_hash"]}
    )
    assert response.status_code == 503
    assert response.json() == {
        "detail": "Too many example pages are live right now. Please try again later."
    }


def test_three_publishes_an_hour_then_429_with_retry_after() -> None:
    client = make(publish_limit_per_hour=3)
    for _ in range(3):
        publish(client)
    preview = client.post(PREVIEW, json=body()).json()
    limited = client.post(
        PUBLISH, json={"draft_id": preview["draft_id"], "config_hash": preview["config_hash"]}
    )
    assert limited.status_code == 429 and int(limited.headers["Retry-After"]) >= 1
    assert limited.json() == {"detail": "Too many requests. Please try again shortly."}


@pytest.mark.parametrize(
    "payload",
    [{}, {"draft_id": "x"}, {"draft_id": "x", "config_hash": "short"},
     {"draft_id": "x", "config_hash": "0" * 64, "extra": 1}],
)  # fmt: skip
def test_bad_publish_bodies_are_422(payload: dict[str, Any]) -> None:
    assert make().post(PUBLISH, json=payload).status_code == 422


def test_publish_and_unpublish_bodies_are_capped_at_one_kilobyte() -> None:
    client = make()
    big = b'{"draft_id":"' + b"a" * 2048 + b'"}'
    for url in (PUBLISH, UNPUBLISH):
        response = client.post(url, content=big, headers={"Content-Type": "application/json"})
        assert response.status_code == 413


# ---- unpublish --------------------------------------------------------------------------------


def test_the_token_unpublishes_and_the_page_then_404s() -> None:
    client = make()
    live = publish(client)
    response = client.post(UNPUBLISH, json={"slug": live["slug"], "token": live["unpublish_token"]})
    assert response.status_code == 200 and response.json() == {"unpublished": True}
    assert client.get(live["public_path"]).status_code == 404


def test_every_refusal_looks_the_same_so_nothing_can_be_probed() -> None:
    client = make()
    live = publish(client)
    attempts = [
        {"slug": live["slug"], "token": "wrong-token-wrong-token-wrong-token"},
        {"slug": "no-such-page", "token": live["unpublish_token"]},
        {"slug": EXAMPLE_SLUG, "token": live["unpublish_token"]},
        {"slug": EXAMPLE_SLUG, "token": "x" * 40},
    ]
    responses = [client.post(UNPUBLISH, json=a) for a in attempts]
    assert {r.status_code for r in responses} == {404}
    assert len({r.text for r in responses}) == 1
    assert responses[0].json() == {"detail": "That unpublish link is not valid."}
    assert client.get(live["public_path"]).status_code == 200


def test_unpublishing_is_rate_limited() -> None:
    client = make()
    codes = [
        client.post(UNPUBLISH, json={"slug": "x-1", "token": "y" * 40}).status_code
        for _ in range(12)
    ]
    assert codes[0] == 404 and codes[-1] == 429


# ---- the example page -------------------------------------------------------------------------


def test_the_example_page_exists_at_startup_with_the_pivot_recommendation() -> None:
    client = make()
    page = client.get(f"/s/{EXAMPLE_SLUG}")
    assert page.status_code == 200 and EXAMPLE_SLUG == "example-pune-cakes"
    assert "Custom celebration cakes" in page.text and "₹1,400" in page.text
    assert "Example" in page.text.split("<h1>")[1].split("</h1>")[0]
    assert "made-up" in page.text and "not a real business" in page.text.lower()


def test_the_example_page_keeps_the_banner_noindex_and_footer() -> None:
    page = make().get(f"/s/{EXAMPLE_SLUG}")
    assert "Example page made with LaunchWise" in page.text
    assert page.headers["x-robots-tag"] == "noindex, nofollow"
    assert 'name="robots" content="noindex, nofollow"' in page.text
    assert "Made with LaunchWise" in page.text


def test_the_example_page_never_expires() -> None:
    clock = FakeClock()
    client = make(clock)
    clock.advance(timedelta(days=3650))
    assert client.get(f"/s/{EXAMPLE_SLUG}").status_code == 200


def test_the_example_page_cannot_be_unpublished_by_any_public_token_flow() -> None:
    client = make()
    for token in ("", "a" * 40, "None", "null"):
        client.post(UNPUBLISH, json={"slug": EXAMPLE_SLUG, "token": token or "z"})
    assert client.get(f"/s/{EXAMPLE_SLUG}").status_code == 200


def test_seeding_is_idempotent_across_restarts_and_the_page_stays_the_same() -> None:
    first = make().get(f"/s/{EXAMPLE_SLUG}").text
    again = make().get(f"/s/{EXAMPLE_SLUG}").text  # a second app on the same database file
    assert first == again


def test_pages_published_before_a_restart_are_still_live_after_it() -> None:
    clock = FakeClock()
    live = publish(make(clock))
    restarted = make(clock)
    assert restarted.get(live["public_path"]).status_code == 200
    clock.advance(PAGE_LIFETIME)
    assert restarted.get(live["public_path"]).status_code == 404


# ---- nothing private leaks --------------------------------------------------------------------


def test_text_tokens_and_clients_never_reach_logs_or_error_bodies(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    client = make()
    live = publish(client, business_name=f"{SENTINEL} Cakes", contact_email="zq@example.com")
    bad = client.post(UNPUBLISH, json={"slug": live["slug"], "token": "w" * 40})
    client.post(UNPUBLISH, json={"slug": live["slug"], "token": live["unpublish_token"]})
    for private in (SENTINEL, SENTINEL.lower(), "zq@example.com", live["unpublish_token"], CLIENT):
        assert private not in caplog.text
        assert private not in bad.text
