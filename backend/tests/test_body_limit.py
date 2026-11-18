"""BodySizeLimitMiddleware: per-path request body caps, by header and by counting bytes."""

from collections.abc import Iterator
from typing import Any

import pytest
from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import JSONResponse
from starlette.routing import Route
from starlette.testclient import TestClient

from app.body_limit import BodySizeLimitMiddleware

LIMIT = 100
PATH = "/limited"
TOO_LARGE = {"detail": "The request body is too large."}


class Probe:
    """Records whether the endpoint ran and how many body bytes it read."""

    def __init__(self) -> None:
        self.calls = 0
        self.bytes_read = 0


def make_client(probe: Probe, limits: dict[str, int] | None = None) -> TestClient:
    async def endpoint(request: Request) -> JSONResponse:
        probe.calls += 1
        body = await request.body()
        probe.bytes_read = len(body)
        return JSONResponse({"read": len(body)})

    app = Starlette(
        routes=[
            Route(PATH, endpoint, methods=["POST", "PUT"]),
            Route("/free", endpoint, methods=["POST"]),
        ]
    )
    app.add_middleware(BodySizeLimitMiddleware, limits=limits or {PATH: LIMIT})
    return TestClient(app)


def chunks(total: int, size: int = 10) -> Iterator[bytes]:
    sent = 0
    while sent < total:
        piece = min(size, total - sent)
        yield b"x" * piece
        sent += piece


def test_a_body_at_the_limit_is_allowed() -> None:
    probe = Probe()
    response = make_client(probe).post(PATH, content=b"x" * LIMIT)
    assert response.status_code == 200 and response.json() == {"read": LIMIT}


def test_one_byte_over_the_limit_is_refused_before_the_endpoint_runs() -> None:
    probe = Probe()
    response = make_client(probe).post(PATH, content=b"x" * (LIMIT + 1))
    assert response.status_code == 413
    assert response.json() == TOO_LARGE
    assert response.headers["content-type"] == "application/json"
    assert probe.calls == 0  # rejected from Content-Length alone, nothing was read


def test_a_streamed_body_with_no_content_length_is_counted_and_refused() -> None:
    probe = Probe()
    client = make_client(probe)
    ok = client.post(PATH, content=chunks(LIMIT))
    assert ok.status_code == 200 and ok.json() == {"read": LIMIT}
    over = client.post(PATH, content=chunks(LIMIT + 1))
    assert over.status_code == 413 and over.json() == TOO_LARGE


def test_a_huge_streamed_body_is_cut_off_early() -> None:
    probe = Probe()
    response = make_client(probe).post(PATH, content=chunks(10_000, size=50))
    assert response.status_code == 413
    assert probe.bytes_read <= LIMIT  # never accumulated the whole thing


def test_a_lying_small_content_length_cannot_smuggle_a_big_body() -> None:
    # The ASGI server enforces framing, so a body can't exceed its declared length; this guards
    # the middleware's own accounting when a header is absent or wrong.
    probe = Probe()
    response = make_client(probe).post(PATH, content=chunks(500), headers={"Content-Length": "5"})
    assert response.status_code in (200, 413)
    assert probe.bytes_read <= LIMIT


@pytest.mark.parametrize("value", ["abc", "-5", "", "1e3"])
def test_a_malformed_content_length_falls_back_to_counting(value: str) -> None:
    probe = Probe()
    response = make_client(probe).post(
        PATH, content=chunks(LIMIT + 1), headers={"Content-Length": value}
    )
    assert response.status_code in (400, 413)


def test_paths_without_a_limit_are_untouched() -> None:
    probe = Probe()
    response = make_client(probe).post("/free", content=b"x" * 10_000)
    assert response.status_code == 200 and response.json() == {"read": 10_000}


def test_every_method_on_a_limited_path_is_covered() -> None:
    probe = Probe()
    response = make_client(probe).put(PATH, content=b"x" * (LIMIT + 1))
    assert response.status_code == 413


def test_limits_are_per_path() -> None:
    probe = Probe()
    client = make_client(probe, {PATH: 10, "/free": 1000})
    assert client.post(PATH, content=b"x" * 11).status_code == 413
    assert client.post("/free", content=b"x" * 11).status_code == 200


def test_non_http_scopes_pass_straight_through() -> None:
    seen: list[str] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        seen.append(scope["type"])

    middleware = BodySizeLimitMiddleware(inner, limits={PATH: 1})

    async def run() -> None:
        await middleware({"type": "lifespan"}, None, None)  # type: ignore[arg-type]

    import asyncio

    asyncio.run(run())
    assert seen == ["lifespan"]
