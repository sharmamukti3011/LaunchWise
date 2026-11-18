"""Per-path request body size limits, as a plain ASGI middleware.

Caddy already caps these paths in front of the app. This is the backstop for anything that
reaches the backend another way, and it keeps the limit under test. A declared Content-Length over
the cap is refused before anything is read; a body with no usable Content-Length (chunked) is
counted as it arrives and refused the moment it passes the cap, so it is never buffered whole.
"""

import json
from collections.abc import Mapping

from starlette.requests import ClientDisconnect
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from app.api_errors import BODY_TOO_LARGE_DETAIL

_BODY = json.dumps({"detail": BODY_TOO_LARGE_DETAIL}).encode()


async def _too_large(send: Send) -> None:
    await send(
        {
            "type": "http.response.start",
            "status": 413,
            "headers": [
                (b"content-type", b"application/json"),
                (b"content-length", str(len(_BODY)).encode()),
            ],
        }
    )
    await send({"type": "http.response.body", "body": _BODY})


def _declared_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", []):
        if name == b"content-length":
            try:
                length = int(value)
            except ValueError:
                return None
            return length if length >= 0 else None
    return None


class BodySizeLimitMiddleware:
    def __init__(self, app: ASGIApp, limits: Mapping[str, int]) -> None:
        self._app = app
        self._limits = dict(limits)

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        limit = self._limits.get(scope["path"]) if scope["type"] == "http" else None
        if limit is None:
            await self._app(scope, receive, send)
            return

        declared = _declared_length(scope)
        if declared is not None and declared > limit:
            await _too_large(send)
            return

        received = 0
        refused = False

        async def counting_receive() -> Message:
            nonlocal received, refused
            if refused:
                return {"type": "http.disconnect"}
            message = await receive()
            if message["type"] == "http.request":
                received += len(message.get("body", b""))
                if received > limit:
                    refused = True
                    await _too_large(send)
                    return {"type": "http.disconnect"}
            return message

        async def guarded_send(message: Message) -> None:
            if not refused:  # once we've answered 413, the app's own reply is dropped
                await send(message)

        try:
            await self._app(scope, counting_receive, guarded_send)
        except ClientDisconnect:
            # The app saw the "disconnect" we fed it after answering 413. That is expected, not an
            # error to log or re-raise. Any other disconnect is a real one and still propagates.
            if not refused:
                raise
