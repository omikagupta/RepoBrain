import asyncio
import json
from collections.abc import Iterator
from hashlib import sha256
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.database.models import (
    GraphAnalysis,
    IngestionState,
    Repository,
    RepositorySnapshot,
    SearchIndex,
    SourceChunk,
    SourceFile,
)
from repobrain.graph.analyzer import Analyzer, GraphError, InputFile, Node
from repobrain.main import create_app
from repobrain.search import service
from repobrain.search.chunking import MAX_BYTES, MAX_LINES, VERSION, chunk_file
from repobrain.settings import Settings

SHA = "d" * 40
SPECIAL = "examples/é #?%.py"
FIXTURE = {
    "src/pkg/__init__.py": "",
    "src/pkg/tools.py": (
        "import os\r\n\r\nclass Loader:\r\n"
        "    @staticmethod\r\n"
        "    def load_item(value):\r\n"
        "        def inner():\r\n"
        "            return value\r\n"
        "        return inner()\r\n"
        "\r\n# module footer\r\n"
    ),
    "examples/a.py": "load_item(1)\n",
    SPECIAL: "load_item(1)\n",
    "broken.py": "def broken(:\r",
}


def test_symbol_chunks_are_disjoint_and_stable() -> None:
    snapshot = uuid4()
    source = InputFile(id=uuid4(), path="tools.py", content=FIXTURE["src/pkg/tools.py"])
    graph = Analyzer(snapshot, [source]).build()
    chunks = list(chunk_file(snapshot, source, graph.nodes))
    repeat = list(chunk_file(snapshot, source, list(reversed(graph.nodes))))
    assert [chunk.id for chunk in chunks] == [chunk.id for chunk in repeat]
    assert [chunk.token_text for chunk in chunks] == [
        chunk.token_text for chunk in repeat
    ]
    assert [(chunk.start_line, chunk.end_line) for chunk in chunks] == [
        (1, 2),
        (3, 3),
        (4, 8),
        (9, 10),
    ]
    assert chunks[2].content.startswith("    @staticmethod\r\n")
    assert "def inner" in chunks[2].content
    assert "".join(chunk.content for chunk in chunks) == source.content


@pytest.mark.parametrize("ending", ["\n", "\r\n", "\r"])
def test_fallback_preserves_original_newlines_and_eof(ending: str) -> None:
    snapshot = uuid4()
    content = ending * (MAX_LINES + 1) + "def invalid(:"
    source = InputFile(id=uuid4(), path="broken.py", content=content)
    graph = Analyzer(snapshot, [source]).build()
    chunks = list(chunk_file(snapshot, source, graph.nodes))
    assert [(item.start_line, item.end_line) for item in chunks] == [
        (1, MAX_LINES),
        (MAX_LINES + 1, MAX_LINES + 2),
    ]
    assert "".join(chunk.content for chunk in chunks) == content
    empty = source.model_copy(update={"content": ""})
    assert list(chunk_file(snapshot, empty, [])) == []


def test_long_definitions_use_bounded_windows_and_large_single_lines_fail() -> None:
    snapshot = uuid4()
    content = (
        "def long_function():\n" + ("    # " + "x" * 100 + "\n") * 90 + "    pass\n"
    )
    source = InputFile(id=uuid4(), path="long.py", content=content)
    chunks = list(
        chunk_file(snapshot, source, Analyzer(snapshot, [source]).build().nodes)
    )
    assert len(chunks) > 1
    assert all(len(chunk.content.encode()) <= MAX_BYTES for chunk in chunks)
    assert all(chunk.end_line - chunk.start_line < MAX_LINES for chunk in chunks)
    assert "".join(chunk.content for chunk in chunks) == content
    with pytest.raises(GraphError, match="line exceeds"):
        list(
            chunk_file(
                snapshot, source.model_copy(update={"content": "é" * MAX_BYTES}), []
            )
        )


async def seed(
    sessions: async_sessionmaker[AsyncSession],
    state: IngestionState = IngestionState.COMPLETED,
) -> UUID:
    async with sessions.begin() as session:
        repository = Repository(owner="sample", name=f"lexical-{uuid4().hex}")
        session.add(repository)
        await session.flush()
        snapshot = RepositorySnapshot(
            repository_id=repository.id, commit_sha=SHA, ingestion_state=state
        )
        session.add(snapshot)
        await session.flush()
        session.add_all(
            SourceFile(
                snapshot_id=snapshot.id,
                path=path,
                content=source,
                language="python",
                line_count=len(source.splitlines()),
                content_sha256=sha256(source.encode()).hexdigest(),
            )
            for path, source in FIXTURE.items()
        )
        return snapshot.id


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_lexical_baseline_ranks_persisted_evidence(
    migrated_database: Settings,
) -> None:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    try:
        snapshot = await seed(sessions)
        other = await seed(sessions)
        first, second = await asyncio.gather(
            service.build_index(sessions, snapshot),
            service.build_index(sessions, snapshot),
        )
        assert sorted((first.reused, second.reused)) == [False, True]
        assert first.chunk_count == second.chunk_count == 7
        assert first.indexed_bytes == sum(
            len(source.encode()) for source in FIXTURE.values()
        )
        await service.build_index(sessions, other)
        app = create_app(migrated_database)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client,
        ):
            url = f"/api/v1/snapshots/{snapshot}/search/lexical"
            response = await client.get(url, params={"q": "load_item"})
            assert response.status_code == 200, response.text
            hitlist = service.SearchResponse.model_validate(response.json())
            assert hitlist.chunking_version == VERSION and hitlist.commit_sha == SHA
            hits = hitlist.results
            assert [hit.rank for hit in hits] == [1, 2, 3]
            assert [hit.path for hit in hits] == [
                "src/pkg/tools.py",
                "examples/a.py",
                SPECIAL,
            ]
            assert hits[0].score > hits[1].score == hits[2].score > 0
            print(
                json.dumps(
                    {
                        "query": hitlist.query,
                        "chunk_count": first.chunk_count,
                        "results": [
                            [
                                hit.rank,
                                hit.path,
                                hit.start_line,
                                hit.end_line,
                                hit.score,
                            ]
                            for hit in hits
                        ],
                    },
                    ensure_ascii=False,
                )
            )
            assert (
                await client.get(url, params={"q": "load_item"})
            ).json() == response.json()
            for term in ("Loader.load_item", "pkg.tools.Loader.load_item"):
                dotted = await client.get(url, params={"q": term})
                assert dotted.status_code == 200, dotted.text
                dotted_ids = [item["chunk_id"] for item in dotted.json()["results"]]
                assert dotted_ids == [str(hits[0].chunk_id)]
            split = await client.get(url, params={"q": "load item", "limit": 1})
            assert len(split.json()["results"]) == 1
            assert (await client.get(url, params={"q": "load_ite"})).json()[
                "results"
            ] == []
        assert hits[2].permalink.endswith(
            f"/blob/{SHA}/examples/%C3%A9%20%23%3F%25.py#L1"
        )
        async with sessions() as session:
            assert await session.get(GraphAnalysis, snapshot) is None
            for hit in hits:
                assert hit.snapshot_id == snapshot
                chunk = await session.get_one(SourceChunk, hit.chunk_id)
                original = FIXTURE[hit.path]
                evidence = "".join(
                    original.splitlines(keepends=True)[
                        hit.start_line - 1 : hit.end_line
                    ]
                )
                assert chunk.content == hit.text == evidence
                assert hit.content_sha256 == sha256(evidence.encode()).hexdigest()
                assert hit.source_sha256 == sha256(original.encode()).hexdigest()
            wrong_file = await session.scalar(
                select(SourceFile.id).where(SourceFile.snapshot_id == other).limit(1)
            )
            assert wrong_file is not None
        with pytest.raises(IntegrityError):
            async with sessions.begin() as session:
                session.add(
                    SourceChunk(
                        id=uuid4(),
                        snapshot_id=snapshot,
                        chunking_version=VERSION,
                        source_file_id=wrong_file,
                        stable_key="0" * 64,
                        start_line=1,
                        end_line=1,
                        content="wrong",
                        source_sha256="0" * 64,
                        content_sha256="0" * 64,
                        token_text="wrong",
                    )
                )
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_build_failure_rolls_back_and_api_errors_are_safe(
    migrated_database: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    original = chunk_file

    def broken(
        snapshot: UUID, source: InputFile, nodes: list[Node]
    ) -> Iterator[SourceChunk]:
        for chunk in original(snapshot, source, nodes):
            chunk.source_file_id = uuid4()
            yield chunk

    try:
        pending = await seed(sessions, IngestionState.PENDING)
        completed = await seed(sessions)
        with monkeypatch.context() as patch:
            patch.setattr(service, "chunk_file", broken)
            with pytest.raises(IntegrityError):
                await service.build_index(sessions, completed)
        async with sessions() as session:
            assert await session.get(SearchIndex, completed) is None
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(SourceChunk)
                    .where(SourceChunk.snapshot_id == completed)
                )
                == 0
            )
        app = create_app(migrated_database)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client,
        ):
            for snapshot, status, error in [
                (pending, 409, "snapshot_incomplete"),
                (completed, 409, "search_index_unavailable"),
                (uuid4(), 404, "snapshot_not_found"),
            ]:
                response = await client.get(
                    f"/api/v1/snapshots/{snapshot}/search/lexical",
                    params={"q": "load_item"},
                    headers={"X-Request-ID": "lexical-review"},
                )
                assert response.status_code == status, response.text
                assert response.json()["error"]["code"] == error
                assert (
                    response.json()["error"]["request_id"]
                    == response.headers["X-Request-ID"]
                )
            url = f"/api/v1/snapshots/{completed}/search/lexical"
            for params in (
                {"q": ""},
                {"q": " !...___"},
                {"q": "x", "limit": "31"},
                {"q": "x" * 257},
            ):
                assert (await client.get(url, params=params)).status_code == 422
        assert (await service.build_index(sessions, completed)).chunk_count == 7
        async with sessions.begin() as session:
            session.add(
                SearchIndex(
                    snapshot_id=pending,
                    chunking_version="future",
                    chunk_count=0,
                    indexed_bytes=0,
                    indexed_files=0,
                )
            )
            row = await session.get_one(RepositorySnapshot, pending)
            row.ingestion_state = IngestionState.COMPLETED
        with pytest.raises(GraphError, match="different chunking version"):
            await service.build_index(sessions, pending)
    finally:
        await engine.dispose()
