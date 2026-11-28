import asyncio
from collections.abc import AsyncIterator

import httpx
import pytest
from starlette.types import Receive, Scope, Send

from repobrain.hosted_bounds import MAX_REQUEST, MAX_RESPONSE, HostedBounds
from repobrain.observability import RequestMiddleware
from repobrain.settings import Settings


@pytest.mark.asyncio
async def test_streams_are_bounded_before_forwarding() -> None:
    entered = False

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        nonlocal entered
        entered = True
        await receive()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        for _ in range(2):
            await send(
                {
                    "type": "http.response.body",
                    "body": b"x" * MAX_RESPONSE,
                    "more_body": True,
                }
            )
        await send({"type": "http.response.body", "body": b""})

    async def chunks() -> AsyncIterator[bytes]:
        yield b"x" * MAX_REQUEST
        yield b"x"

    transport = httpx.ASGITransport(
        app=RequestMiddleware(HostedBounds(app, Settings()))
    )
    async with httpx.AsyncClient(
        transport=transport, base_url="http://local"
    ) as client:
        rejected = await client.post("/api", content=chunks())
        assert rejected.status_code == 413 and not entered
        response = await client.get("/api")
        assert response.status_code == 413 and entered
        assert response.json()["error"]["code"] == "response_limit"


@pytest.mark.asyncio
async def test_admission_and_body_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("repobrain.hosted_bounds.BODY_TIMEOUT", 0.05)
    admitted = asyncio.Event()
    release = asyncio.Event()

    async def app(scope: Scope, receive: Receive, send: Send) -> None:
        await receive()
        admitted.set()
        await release.wait()
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": b"ok"})

    async def stalled() -> AsyncIterator[bytes]:
        yield b"x"
        await asyncio.Event().wait()

    bounds = HostedBounds(app, Settings(hosted_inflight_requests=2))
    transport = httpx.ASGITransport(app=RequestMiddleware(bounds))
    async with httpx.AsyncClient(
        transport=transport, base_url="http://local"
    ) as client:
        timed_out = await client.post("/api", content=stalled())
        assert timed_out.status_code == 408 and bounds.active == 0
        async with asyncio.timeout(3):
            first = asyncio.create_task(client.get("/api"))
            second = asyncio.create_task(client.get("/api"))
            try:
                await admitted.wait()
                while bounds.active < 2:
                    await asyncio.sleep(0)
                denied = await client.get("/api")
                assert denied.status_code == 429 and "Retry-After" in denied.headers
            finally:
                release.set()
                await asyncio.gather(first, second)
        assert bounds.active == 0
