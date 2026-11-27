import asyncio
from collections.abc import Callable

import pytest

from repobrain.graph.exploration import ExplorationError
from repobrain.search.embedding import Inference, LocalOnnxProvider


class ControlledNative:
    def __init__(self) -> None:
        self.started: dict[str, asyncio.Event] = {}
        self.finish: dict[str, asyncio.Event] = {}
        self.jobs: dict[str, Inference] = {}

    def start_event(self, name: str) -> asyncio.Event:
        return self.started.setdefault(name, asyncio.Event())

    def finish_event(self, name: str) -> asyncio.Event:
        return self.finish.setdefault(name, asyncio.Event())

    async def __call__(
        self,
        infer: Callable[[list[str], Inference], list[list[float]]],
        texts: list[str],
        job: Inference,
    ) -> list[list[float]]:
        name = texts[0]
        self.jobs[name] = job
        self.start_event(name).set()
        await self.finish_event(name).wait()
        return [[1.0]]


async def submit(
    group: asyncio.TaskGroup,
    provider: LocalOnnxProvider,
    name: str,
) -> asyncio.Task[list[list[float]]]:
    ready = asyncio.Event()

    async def run() -> list[list[float]]:
        ready.set()
        return await provider.encode_queries([name])

    job = group.create_task(run())
    await ready.wait()
    return job


@pytest.mark.asyncio
async def test_bounded_fifo_and_queued_cancellation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    native = ControlledNative()
    monkeypatch.setattr(asyncio, "to_thread", native)
    provider = LocalOnnxProvider(None)
    async with asyncio.timeout(5), asyncio.TaskGroup() as group:
        first = await submit(group, provider, "first")
        await native.start_event("first").wait()
        skipped = await submit(group, provider, "skipped")
        next_job = await submit(group, provider, "next")
        with pytest.raises(ExplorationError, match="busy"):
            await provider.encode_queries(["overflow"])
        skipped.cancel()
        with pytest.raises(asyncio.CancelledError):
            await skipped
        last = await submit(group, provider, "last")
        assert list(native.jobs) == ["first"]
        native.finish_event("first").set()
        await native.start_event("next").wait()
        assert await first == [[1.0]]
        assert list(native.jobs) == ["first", "next"]
        native.finish_event("next").set()
        await native.start_event("last").wait()
        assert await next_job == [[1.0]]
        native.finish_event("last").set()
        assert await last == [[1.0]]
    assert provider.admitted == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("reason", ["cancel", "timeout"])
async def test_running_job_owns_slot_until_native_exit(
    monkeypatch: pytest.MonkeyPatch,
    reason: str,
) -> None:
    native = ControlledNative()
    monkeypatch.setattr(asyncio, "to_thread", native)
    provider = LocalOnnxProvider(None)
    deadline = asyncio.timeout(None)
    started = asyncio.Event()

    async def active() -> None:
        started.set()
        if reason == "timeout":
            with pytest.raises(ExplorationError, match="timed out"):
                await provider.encode_queries(["active"])
        else:
            await provider.encode_queries(["active"])

    async with asyncio.timeout(5), asyncio.TaskGroup() as group:
        with monkeypatch.context() as patch:
            patch.setattr(asyncio, "timeout", lambda _: deadline)
            first = group.create_task(active())
            await started.wait()
            await native.start_event("active").wait()
        waiting = await submit(group, provider, "waiting")
        if reason == "timeout":
            deadline.reschedule(asyncio.get_running_loop().time())
            await first
        else:
            first.cancel()
            with pytest.raises(asyncio.CancelledError):
                await first
        assert native.jobs["active"].cancelled.is_set()
        assert list(native.jobs) == ["active"]
        native.finish_event("active").set()
        await native.start_event("waiting").wait()
        native.finish_event("waiting").set()
        assert await waiting == [[1.0]]
    assert provider.admitted == 0
