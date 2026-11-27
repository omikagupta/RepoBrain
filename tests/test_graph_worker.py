import asyncio
import sys
from collections.abc import Awaitable, Callable
from uuid import uuid4

import pytest

from repobrain.graph import service
from repobrain.graph.analyzer import GraphError


@pytest.mark.asyncio
@pytest.mark.parametrize("interrupt", ["cancel", "timeout", "launch"])
async def test_interrupted_worker_is_killed_and_reaped(
    monkeypatch: pytest.MonkeyPatch, interrupt: str
) -> None:
    spawn = asyncio.create_subprocess_exec
    ready = asyncio.Event()
    deliver = asyncio.Event()
    children: list[asyncio.subprocess.Process] = []
    exchanges = 0

    async def launch(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
        nonlocal exchanges
        assert args[1:4] == ("-I", "-m", "repobrain.graph.worker")
        env = kwargs["env"]
        assert isinstance(env, dict) and "REPOBRAIN_DATABASE_URL" not in env
        process = await spawn(
            sys.executable,
            "-I",
            "-c",
            "import threading; threading.Event().wait()",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        children.append(process)
        communicate: Callable[[bytes | None], Awaitable[tuple[bytes, bytes]]] = (
            process.communicate
        )

        async def exchange(input_: bytes | None = None) -> tuple[bytes, bytes]:
            nonlocal exchanges
            exchanges += 1
            ready.set()
            return await communicate(input_)

        monkeypatch.setattr(process, "communicate", exchange)
        if interrupt == "launch":
            ready.set()
            await deliver.wait()
        return process

    monkeypatch.setenv("REPOBRAIN_DATABASE_URL", "test-sensitive-value")
    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    deadline = asyncio.timeout(None)

    async def parse() -> None:
        async with deadline:
            await service.parse_files(uuid4(), [])

    async with asyncio.timeout(10):
        worker = asyncio.create_task(parse())
        try:
            await ready.wait()
            if interrupt == "timeout":
                deadline.reschedule(asyncio.get_running_loop().time())
                with pytest.raises(TimeoutError):
                    await worker
            else:
                worker.cancel()
                deliver.set()
                with pytest.raises(asyncio.CancelledError):
                    await worker
        finally:
            deliver.set()
            if not worker.done():
                worker.cancel()
                await asyncio.gather(worker, return_exceptions=True)
    assert exchanges == 1
    assert children[0].returncode is not None and children[0].returncode != 0


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "message"),
    [(0, "invalid graph"), (1, "process failed"), (2, "analysis limit")],
)
async def test_worker_errors_never_echo_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    status: int,
    message: str,
) -> None:
    spawn = asyncio.create_subprocess_exec

    async def launch(*args: str, **kwargs: object) -> asyncio.subprocess.Process:
        return await spawn(
            sys.executable,
            "-I",
            "-c",
            "import sys; print('private stdout'); "
            f"print('private stderr', file=sys.stderr); sys.exit({status})",
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )

    monkeypatch.setattr(asyncio, "create_subprocess_exec", launch)
    with pytest.raises(GraphError, match=message) as error:
        await service.parse_files(uuid4(), [])
    assert "private" not in str(error.value)
    output = capsys.readouterr()
    assert output.out == output.err == ""
