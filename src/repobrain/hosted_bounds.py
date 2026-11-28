"""Bound hosted HTTP admission and buffer small API responses."""

import asyncio
from time import monotonic

from starlette.datastructures import Headers, MutableHeaders
from starlette.requests import Request
from starlette.types import ASGIApp, Message, Receive, Scope, Send

from repobrain.observability import error_response
from repobrain.settings import Settings

MAX_REQUEST = 8192
MAX_RESPONSE = 1024 * 1024
BODY_TIMEOUT = 5
REQUEST_TIMEOUT = 75
SEND_TIMEOUT = 5


class HostedBounds:
    def __init__(self, app: ASGIApp, settings: Settings) -> None:
        self.app = app
        self.limit = settings.hosted_inflight_requests
        self.rate = settings.hosted_public_per_minute
        self.active = self.health_active = 0
        self.minute = -1
        self.count = self.health_count = 0

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope)
        health = scope["path"] == "/healthz"
        now = int(monotonic())
        minute = now // 60
        if minute != self.minute:
            self.minute, self.count, self.health_count = minute, 0, 0
        count = self.health_count if health else self.count
        full = self.health_active >= 2 if health else self.active >= self.limit

        async def fail(
            status: int, code: str, message: str, retry: int | None = None
        ) -> None:
            headers = {"Cache-Control": "no-store"}
            if retry is not None:
                headers["Retry-After"] = str(retry)
            response = error_response(request, status, code, message, headers)
            async with asyncio.timeout(SEND_TIMEOUT):
                await response(scope, receive, send)

        if count >= self.rate or full:
            await fail(
                429,
                "request_limit",
                "Service busy. Try again shortly.",
                60 - now % 60 if count >= self.rate else 5,
            )
            return
        if health:
            self.health_count += 1
            self.health_active += 1
        else:
            self.count += 1
            self.active += 1
        try:
            length = request.headers.get("content-length", "0")
            if (
                len(scope["query_string"]) > MAX_REQUEST
                or not length.isascii()
                or not length.isdecimal()
                or len(length) > 10
                or int(length) > MAX_REQUEST
            ):
                await fail(413, "request_limit", "Request is too large")
                return

            body = bytearray()
            too_large = False
            try:
                async with asyncio.timeout(BODY_TIMEOUT):
                    while True:
                        event = await receive()
                        if event["type"] == "http.disconnect":
                            return
                        chunk = event.get("body", b"")
                        if len(body) + len(chunk) > MAX_REQUEST:
                            too_large = True
                            break
                        body.extend(chunk)
                        if not event.get("more_body", False):
                            break
            except TimeoutError:
                await fail(408, "request_timeout", "Request body timed out")
                return
            if too_large:
                await fail(413, "request_limit", "Request is too large")
                return

            pending = True
            response_start: Message | None = None
            output = bytearray()
            oversized = False

            async def replay() -> Message:
                nonlocal pending
                if pending:
                    pending = False
                    return {
                        "type": "http.request",
                        "body": bytes(body),
                        "more_body": False,
                    }
                return await receive()

            async def buffer(message: Message) -> None:
                nonlocal response_start, oversized
                if message["type"] == "http.response.start":
                    response_start = message
                    declared = Headers(scope=message).get("content-length", "0")
                    oversized = declared.isdecimal() and (
                        len(declared) > 10 or int(declared) > MAX_RESPONSE
                    )
                    return
                chunk = message.get("body", b"")
                if oversized or len(output) + len(chunk) > MAX_RESPONSE:
                    oversized = True
                    return
                output.extend(chunk)

            try:
                async with asyncio.timeout(REQUEST_TIMEOUT):
                    await self.app(scope, replay, buffer)
            except TimeoutError:
                await fail(504, "request_timeout", "Request timed out")
                return
            if oversized:
                await fail(413, "response_limit", "Request fewer results")
                return
            if response_start is not None:
                MutableHeaders(scope=response_start)["Cache-Control"] = "no-store"
                async with asyncio.timeout(SEND_TIMEOUT):
                    await send(response_start)
                    await send({"type": "http.response.body", "body": bytes(output)})
        finally:
            if health:
                self.health_active -= 1
            else:
                self.active -= 1
