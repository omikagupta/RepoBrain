"""Hosted bounds for requests admitted before authentication."""

import asyncio
from time import monotonic

from starlette.datastructures import Headers
from starlette.exceptions import HTTPException
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from repobrain.observability import error_response
from repobrain.settings import Settings

MAX_REQUEST = 8192
MAX_RESPONSE = 1024 * 1024


class HostedBounds:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.limit = settings.hosted_inflight_requests
        self.rate = settings.hosted_public_per_minute
        self.active = 0
        self.minute = -1
        self.count = 0
        self.health_count = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        minute = int(monotonic() // 60)
        if minute != self.minute:
            self.minute, self.count, self.health_count = minute, 0, 0
        health = scope["path"] == "/healthz"
        count = self.health_count if health else self.count
        if count >= self.rate or (not health and self.active >= self.limit):
            response = error_response(
                request,
                429,
                "request_limit",
                "Service busy. Try again shortly.",
                {
                    "Retry-After": "5"
                    if count < self.rate
                    else str(60 - int(monotonic()) % 60)
                },
            )
            await response(scope, receive, send)
            return
        if health:
            self.health_count += 1
        else:
            self.count += 1
            self.active += 1

        consumed = 0
        deadline = monotonic() + 5
        suppressed = False

        async def bounded_receive() -> Message:
            nonlocal consumed
            try:
                async with asyncio.timeout(max(0, deadline - monotonic())):
                    message = await receive()
            except TimeoutError:
                raise HTTPException(408) from None
            consumed += len(message.get("body", b""))
            if consumed > MAX_REQUEST:
                raise HTTPException(413)
            return message

        async def bounded_send(message: Message) -> None:
            nonlocal suppressed
            if message["type"] == "http.response.start":
                length = Headers(scope=message).get("content-length", "0")
                if length.isdecimal() and int(length) > MAX_RESPONSE:
                    suppressed = True
                    response = error_response(
                        request, 413, "response_limit", "Request fewer results"
                    )
                    await response(scope, receive, send)
            if not suppressed:
                await send(message)

        try:
            if len(scope["query_string"]) > MAX_REQUEST:
                response = error_response(
                    request, 413, "request_limit", "Request is too large"
                )
                await response(scope, receive, send)
            else:
                await self.app(scope, bounded_receive, bounded_send)
        finally:
            if not health:
                self.active -= 1
