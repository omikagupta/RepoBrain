import asyncio
from argparse import Namespace
from pathlib import Path

import pytest

from repobrain.evaluation.__main__ import execute


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("endpoint", "key"),
    [
        ("https://example.invalid/v1/chat/completions", None),
        ("http://127.0.0.1:8800/v1/chat/completions", "fixture-key"),
    ],
)
async def test_answers_cli_rejects_provider_before_loading_inputs(
    endpoint: str, key: str | None, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.setenv("REPOBRAIN_GENERATION_ENDPOINT", endpoint)
    monkeypatch.setenv("REPOBRAIN_GENERATION_MODEL", "fixture")
    if key:
        monkeypatch.setenv("REPOBRAIN_GENERATION_API_KEY", key)
    else:
        monkeypatch.delenv("REPOBRAIN_GENERATION_API_KEY", raising=False)
    # No dataset files or database are available. The provider check comes first.
    with pytest.raises(ValueError, match="keyless loopback provider"):
        await execute(
            Namespace(action="answers", root=tmp_path, version="benchmark-v1")
        )


@pytest.mark.asyncio
async def test_keyless_loopback_passes_provider_gate_without_contacting_provider(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    connected = asyncio.Event()

    async def mock_provider(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        connected.set()
        writer.close()
        await writer.wait_closed()

    async with await asyncio.start_server(mock_provider, "127.0.0.1", 0) as server:
        port = server.sockets[0].getsockname()[1]
        monkeypatch.setenv(
            "REPOBRAIN_GENERATION_ENDPOINT",
            f"http://127.0.0.1:{port}/v1/chat/completions",
        )
        monkeypatch.setenv("REPOBRAIN_GENERATION_MODEL", "fixture")
        monkeypatch.delenv("REPOBRAIN_GENERATION_API_KEY", raising=False)
        with pytest.raises(FileNotFoundError, match="benchmark-v1-freeze.json"):
            await execute(
                Namespace(action="answers", root=tmp_path, version="benchmark-v1")
            )
        assert not connected.is_set()
