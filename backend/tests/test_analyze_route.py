"""POST /api/analyze through the app: happy paths, limits, generic errors, and no data echoes."""

import copy
import json
import logging
from collections.abc import Iterator
from datetime import timedelta
from typing import Any

import pytest
from fastapi.testclient import TestClient

from app.main import create_app
from app.services.demo_catalog import DEMO_DIR
from app.services.market_data import DatasetError
from app.settings import Settings
from tests.fakes import FakeClock, FakeMailSender

URL = "/api/analyze"
SCENARIOS = DEMO_DIR  # the shipped demo files are the only copy of these scenarios
SCENARIO_A = "a_alternative_beats_thin_margin_original"
SENTINEL = "ZQSENTINEL"
INVALID_REQUEST = "The request was not valid."
INVALID_SCENARIO = "The scenario could not be analysed."
TOO_LARGE = {"detail": "The request body is too large."}


def scenario(name: str = SCENARIO_A) -> dict[str, Any]:
    data: dict[str, Any] = json.loads((SCENARIOS / f"{name}.json").read_text())
    return data


def settings(**overrides: Any) -> Settings:
    return Settings(_env_file=None, app_env="test", **overrides)


# A complete fake mailbox, so the contact route is "ready" (no test can reach the network).
MAILBOX: dict[str, Any] = {
    "contact_enabled": True,
    "smtp_host": "smtp.mail.test",
    "smtp_port": 465,
    "smtp_user": "mailbox@mail.test",
    "smtp_password": "s3cret-value-xyz",
    "contact_recipient": "owner@mail.test",
}


def make_client(
    clock: FakeClock | None = None,
    peer: tuple[str, int] = ("203.0.113.7", 50000),
    **setting_overrides: Any,
) -> TestClient:
    app = create_app(settings(**setting_overrides), clock=clock)
    return TestClient(app, client=peer)


@pytest.fixture
def client() -> TestClient:
    return make_client()


# ---- success ----------------------------------------------------------------------------------


def test_the_lead_pune_scenario_returns_the_full_analysis(client: TestClient) -> None:
    response = client.post(URL, json=scenario())
    assert response.status_code == 200
    body = response.json()
    assert body["market_coverage"] == "covered"
    assert body["ranking"]["recommended_id"] == "custom-celebration-cakes"
    assert body["ranking"]["keep_original"] is False
    assert [s["option_id"] for s in body["ranking"]["ranked"]][0] == "custom-celebration-cakes"
    assert [step["tool"] for step in body["steps"]][0] == "validate_constraints"
    assert body["steps"][-1]["tool"] == "compare_strategies"
    assert body["analyzed_on"] == "2026-11-17" or len(body["analyzed_on"]) == 10


def test_money_in_the_response_is_never_a_float(client: TestClient) -> None:
    body = client.post(URL, json=scenario()).json()

    def walk(node: Any) -> None:
        assert not isinstance(node, float)
        if isinstance(node, dict):
            for value in node.values():
                walk(value)
        elif isinstance(node, list):
            for value in node:
                walk(value)

    walk(body)
    assert body["options"][0]["feasibility"]["startup_cost"]["value"] == "3000.00"


def test_the_noida_scenario_is_a_200_with_market_coverage_none(client: TestClient) -> None:
    response = client.post(URL, json=scenario("d_noida_feasibility_only"))
    assert response.status_code == 200
    body = response.json()
    assert body["market_coverage"] == "none"
    assert "feasibility-only" in body["market_message"]
    assert body["skipped_option_ids"] == ["pune-cake-pivot"]
    assert body["evidence"] == []
    assert body["ranking"]["keep_original"] is True


@pytest.mark.parametrize("name", ["b_strong_original_wins", "c_no_viable_option"])
def test_the_other_saved_scenarios_return_200(client: TestClient, name: str) -> None:
    assert client.post(URL, json=scenario(name)).status_code == 200


def test_the_response_is_identical_for_identical_requests(client: TestClient) -> None:
    first = client.post(URL, json=scenario()).text
    assert client.post(URL, json=scenario()).text == first


# ---- generic errors ---------------------------------------------------------------------------


def assert_generic_422(response: Any) -> list[dict[str, str]]:
    assert response.status_code == 422
    body = response.json()
    assert set(body) == {"detail", "errors"}
    assert body["detail"] in {INVALID_REQUEST, INVALID_SCENARIO}
    for error in body["errors"]:
        assert set(error) == {"field", "message"}  # no input, no ctx, no url, no type
    errors: list[dict[str, str]] = body["errors"]
    return errors


def test_an_invalid_field_names_its_path_and_never_echoes_its_value(client: TestClient) -> None:
    body = scenario()
    body["options"][1]["price"] = "not-a-number-4242"
    errors = assert_generic_422(client.post(URL, json=body))
    assert errors[0]["field"] == "options.1.price"
    assert "4242" not in json.dumps(errors)


def test_an_unknown_field_is_reported_without_echoing_its_name(client: TestClient) -> None:
    body = scenario()
    body["profile"][f"{SENTINEL}-name"] = "x"
    response = client.post(URL, json=body)
    errors = assert_generic_422(response)
    assert errors == [{"field": "profile", "message": "Unknown field."}]
    assert SENTINEL not in response.text


def test_malformed_and_empty_bodies_are_generic_422s(client: TestClient) -> None:
    for content in (b"{not json", b"", b"[]", b"null", b'"text"'):
        response = client.post(URL, content=content, headers={"Content-Type": "application/json"})
        assert_generic_422(response)
        assert "not json" not in response.text


def test_wrong_field_types_use_fixed_messages(client: TestClient) -> None:
    body = scenario()
    body["profile"]["units_per_day"] = {"a": "b"}
    errors = assert_generic_422(client.post(URL, json=body))
    assert errors[0]["field"] == "profile.units_per_day"


def test_a_float_money_value_is_rejected_generically(client: TestClient) -> None:
    body = scenario()
    body["profile"]["budget"] = 10000.5
    errors = assert_generic_422(client.post(URL, json=body))
    assert errors[0]["field"] == "profile.budget"


def test_option_count_and_original_rules_are_reported_on_options(client: TestClient) -> None:
    body = scenario()
    body["options"] = []
    assert assert_generic_422(client.post(URL, json=body))[0]["field"] == "options"
    body = scenario()
    body["options"] = [dict(body["options"][1]) for _ in range(1)]
    assert assert_generic_422(client.post(URL, json=body))[0]["field"] == "options"
    body = scenario()
    body["options"] = body["options"] * 3  # 9 options: too many (and duplicate ids)
    assert assert_generic_422(client.post(URL, json=body))


def test_at_most_ten_errors_are_returned(client: TestClient) -> None:
    body = scenario()
    for option in body["options"]:
        for key in ("price", "variable_cost_per_unit", "fixed_startup_costs"):
            option[key] = "bad"
    body["profile"]["budget"] = "bad"
    body["profile"]["units_per_day"] = "bad"
    assert len(assert_generic_422(client.post(URL, json=body))) <= 10


def test_an_unknown_market_link_is_a_fixed_text_scenario_error(client: TestClient) -> None:
    body = scenario()
    body["options"][1]["opportunity_id"] = f"{SENTINEL}-OPP"
    response = client.post(URL, json=body)
    errors = assert_generic_422(response)
    assert response.json()["detail"] == INVALID_SCENARIO
    assert errors == [
        {
            "field": "options.1.opportunity_id",
            "message": "An option links to market evidence that is not in the dataset.",
        }
    ]
    assert SENTINEL not in response.text


def test_the_validation_error_shape_also_applies_to_the_contact_route() -> None:
    client = make_client(**MAILBOX)
    response = client.post("/api/contact", json={"name": "A", "email": "nope", "message": "short"})
    assert_generic_422(response)


# ---- body size --------------------------------------------------------------------------------

ANALYZE_LIMIT = 32 * 1024
CONTACT_LIMIT = 16 * 1024


def padded(limit: int, body: dict[str, Any] | None = None, extra: int = 0) -> bytes:
    """A valid JSON request padded with trailing spaces to exactly `limit + extra` bytes."""
    raw = json.dumps(body or scenario()).encode()
    return raw + b" " * (limit + extra - len(raw))


def test_a_request_at_the_size_limit_is_processed(client: TestClient) -> None:
    response = client.post(URL, content=padded(ANALYZE_LIMIT), headers=JSON)
    assert response.status_code == 200


def test_one_byte_over_the_limit_is_413_with_a_generic_body(client: TestClient) -> None:
    response = client.post(URL, content=padded(ANALYZE_LIMIT, extra=1), headers=JSON)
    assert response.status_code == 413
    assert response.json() == TOO_LARGE


def test_a_streamed_oversize_body_is_refused_too(client: TestClient) -> None:
    def stream() -> Iterator[bytes]:
        data = padded(ANALYZE_LIMIT, extra=500)
        for i in range(0, len(data), 1024):
            yield data[i : i + 1024]

    response = client.post(URL, content=stream(), headers=JSON)
    assert response.status_code == 413
    assert response.json() == TOO_LARGE


def test_an_oversize_body_with_sentinels_is_not_echoed(client: TestClient) -> None:
    body = scenario()
    body["category"] = SENTINEL
    response = client.post(URL, content=padded(ANALYZE_LIMIT, body, 1), headers=JSON)
    assert response.status_code == 413 and SENTINEL not in response.text


def test_the_contact_endpoint_has_its_own_smaller_limit() -> None:
    app = create_app(settings(**MAILBOX), mail_sender=FakeMailSender())
    client = TestClient(app)
    small = json.dumps({"name": "Asha", "email": "a@b.com", "message": "x" * 20}).encode()
    over = small + b" " * (CONTACT_LIMIT + 1 - len(small))
    assert client.post("/api/contact", content=over, headers=JSON).status_code == 413
    ok = small + b" " * (CONTACT_LIMIT - len(small))
    assert client.post("/api/contact", content=ok, headers=JSON).status_code == 200


def test_health_is_not_body_limited(client: TestClient) -> None:
    assert client.get("/api/health").status_code == 200


JSON = {"Content-Type": "application/json"}


# ---- rate limiting ----------------------------------------------------------------------------


def test_the_61st_request_in_a_minute_is_429_with_retry_after() -> None:
    clock = FakeClock()
    client = make_client(clock)
    body = scenario("d_noida_feasibility_only")
    assert [client.post(URL, json=body).status_code for _ in range(60)] == [200] * 60
    refused = client.post(URL, json=body)
    assert refused.status_code == 429
    assert refused.headers["retry-after"] == "60"
    assert set(refused.json()) == {"detail"}
    clock.advance(timedelta(seconds=60))
    assert client.post(URL, json=body).status_code == 200


def test_the_limit_comes_from_settings_and_clients_are_independent() -> None:
    clock = FakeClock()
    app = create_app(settings(analyze_rate_limit_per_ip=2), clock=clock)
    first = TestClient(app, client=("198.51.100.1", 50000))
    second = TestClient(app, client=("198.51.100.2", 50000))
    body = scenario("d_noida_feasibility_only")
    assert [first.post(URL, json=body).status_code for _ in range(3)] == [200, 200, 429]
    assert [second.post(URL, json=body).status_code for _ in range(3)] == [200, 200, 429]


def test_invalid_requests_do_not_use_up_the_analysis_budget() -> None:
    client = make_client(analyze_rate_limit_per_ip=1)
    for _ in range(5):
        assert client.post(URL, json={}).status_code == 422
    assert client.post(URL, json=scenario("d_noida_feasibility_only")).status_code == 200


# ---- CORS and reserved paths ------------------------------------------------------------------


def test_cors_allows_only_the_configured_origin(client: TestClient) -> None:
    body = scenario("d_noida_feasibility_only")
    allowed = client.post(URL, json=body, headers={"Origin": "http://localhost:5173"})
    blocked = client.post(URL, json=body, headers={"Origin": "https://evil.example"})
    assert allowed.headers.get("access-control-allow-origin") == "http://localhost:5173"
    assert "access-control-allow-origin" not in blocked.headers


def test_a_413_still_carries_cors_headers_for_the_allowed_origin(client: TestClient) -> None:
    headers = {**JSON, "Origin": "http://localhost:5173"}
    response = client.post(URL, content=padded(ANALYZE_LIMIT, extra=1), headers=headers)
    assert response.status_code == 413
    assert response.headers.get("access-control-allow-origin") == "http://localhost:5173"


def test_the_storefront_path_prefix_is_reserved() -> None:
    app = create_app(settings())
    registered = list(app.openapi()["paths"])
    assert sorted(registered) == [
        "/api/analyze",
        "/api/analyze/explain",
        "/api/contact",
        "/api/demo/explain/{scenario_id}",
        "/api/demo/run/{scenario_id}",
        "/api/demo/scenarios",
        "/api/health",
        "/api/market-evidence",
    ]
    assert [p for p in registered if p == "/s" or p.startswith("/s/")] == []
    client = TestClient(app)
    for path in ("/s", "/s/", "/s/some-bakery"):
        assert client.get(path).status_code == 404  # nothing here squats the storefront prefix


# ---- startup ----------------------------------------------------------------------------------


def test_a_bad_dataset_stops_the_app_from_starting(monkeypatch: pytest.MonkeyPatch) -> None:
    def broken(*args: Any, **kwargs: Any) -> None:
        raise DatasetError("dataset file is not valid JSON")

    monkeypatch.setattr("app.main.load_dataset", broken)
    with pytest.raises(DatasetError):
        create_app(settings())


# ---- sentinels: nothing the visitor sends comes back in an error or a log line ----------------


def leaf_paths(node: Any, prefix: tuple[Any, ...] = ()) -> Iterator[tuple[Any, ...]]:
    if isinstance(node, dict):
        for key, value in node.items():
            yield from leaf_paths(value, (*prefix, key))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            yield from leaf_paths(value, (*prefix, index))
    else:
        yield prefix


def get(node: Any, path: tuple[Any, ...]) -> Any:
    for key in path:
        node = node[key]
    return node


def put(node: Any, path: tuple[Any, ...], value: Any) -> None:
    for key in path[:-1]:
        node = node[key]
    node[path[-1]] = value


BASE = scenario()
PATHS = list(leaf_paths(BASE))
TEXT_PATHS = [p for p in PATHS if isinstance(get(BASE, p), str) and p[-1] not in {"source"}]


def label(path: tuple[Any, ...]) -> str:
    return ".".join(str(p) for p in path)


@pytest.mark.parametrize("path", PATHS, ids=label)
def test_a_sentinel_in_any_field_never_comes_back_in_an_error_or_a_log_line(
    path: tuple[Any, ...], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    original = get(BASE, path)
    sentinel = f"{SENTINEL}-{label(path)}"
    # Strings get a NUL after the sentinel: never valid text, and not trimmed away like a trailing
    # newline would be, so the request must fail. Numbers and booleans get a sentinel string,
    # which is the wrong type.
    bad = f"{sentinel}\x00tail" if isinstance(original, str) else sentinel
    body = copy.deepcopy(BASE)
    put(body, path, bad)
    response = make_client().post(URL, json=body)
    assert response.status_code == 422, f"{label(path)} unexpectedly accepted"
    assert sentinel not in response.text
    assert SENTINEL not in caplog.text


@pytest.mark.parametrize("path", TEXT_PATHS, ids=label)
def test_a_valid_sentinel_text_is_never_logged(
    path: tuple[Any, ...], caplog: pytest.LogCaptureFixture
) -> None:
    caplog.set_level(logging.DEBUG)
    body = copy.deepcopy(BASE)
    # Option ids and market links must keep their shape; everything else is free text.
    value = f"{SENTINEL}-ok" if path[-1] != "id" else "zqsentinel-ok"
    if path[-1] == "opportunity_id":
        value = f"{SENTINEL}-OPP"
    put(body, path, value)
    make_client().post(URL, json=body)  # may succeed or be a scenario error: either is fine
    assert SENTINEL.lower() not in caplog.text.lower()


def test_sentinels_in_every_field_at_once_and_in_unknown_keys(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    client = make_client()
    body = copy.deepcopy(BASE)
    for path in PATHS:
        put(body, path, f"{SENTINEL}-{label(path)}\x00tail")
    response = client.post(URL, json=body)
    assert response.status_code == 422 and SENTINEL not in response.text

    for where in ((), ("profile",), ("options", 0), ("profile", "hours_per_week")):
        body = copy.deepcopy(BASE)
        target = get(body, where)
        target[f"{SENTINEL}-key"] = f"{SENTINEL}-value"
        response = client.post(URL, json=body)
        assert response.status_code == 422 and SENTINEL not in response.text

    assert SENTINEL not in caplog.text
