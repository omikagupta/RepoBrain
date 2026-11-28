import asyncio
import json
import math
from collections.abc import Sequence
from hashlib import sha256
from pathlib import Path
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.database.models import (
    ChunkEmbedding,
    IngestionState,
    Repository,
    RepositorySnapshot,
    SourceChunk,
    SourceFile,
    VectorIndex,
)
from repobrain.graph.exploration import ExplorationError
from repobrain.main import create_app
from repobrain.search import vector
from repobrain.search.chunking import VERSION
from repobrain.search.embedding import (
    DIMENSION,
    MODEL,
    EmbeddingModel,
    LocalOnnxProvider,
    normalize,
)
from repobrain.search.service import build_index
from repobrain.settings import Settings

SYNTHETIC = EmbeddingModel(
    model_id="fixture/synthetic",
    revision="fixture-v1",
    dimension=DIMENSION,
    encoding_policy="two-coordinates-v1",
)
SHA = "c" * 40
SPECIAL = "src/é #%.py"
CORPUS = {
    "a.py": "read_file = 1\n",
    SPECIAL: "read_file = 2\r\n",
    "near.py": "read_bytes = 3\r",
    "far.py": "add = 4\n",
}


def point(x: float, y: float) -> list[float]:
    return [x, y] + [0] * (DIMENSION - 2)


class FakeProvider:
    def __init__(self, model: EmbeddingModel = SYNTHETIC) -> None:
        self.model = model
        self.batches: list[int] = []
        self.entered = asyncio.Event()
        self.release: asyncio.Event | None = None

    async def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        self.batches.append(len(texts))
        self.entered.set()
        if self.release is not None:
            await self.release.wait()
        return [
            point(5, 0)
            if "read_file" in item
            else point(3, 4)
            if "read_bytes" in item
            else point(-1, 0)
            for item in texts
        ]

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        return [point(2, 0) for _ in texts]


@pytest.mark.parametrize("values", [[], [1], [0, 0], [math.nan, 1], [math.inf, 1]])
def test_normalization_rejects_invalid_vectors(values: list[float]) -> None:
    with pytest.raises(ExplorationError, match="invalid vectors"):
        normalize([values], 1, 2)


def test_normalization_handles_large_finite_values() -> None:
    values = normalize([[1e308, 1e308]], 1, 2)[0]
    assert math.hypot(*values) == pytest.approx(1)
    with pytest.raises(ExplorationError):
        normalize([], 1, 2)


@pytest.mark.asyncio
async def test_provider_is_lazy_and_missing_weights_are_safe(tmp_path: Path) -> None:
    local = LocalOnnxProvider(tmp_path)
    assert local.model == MODEL and local.runtime is None and local.task is None
    app = create_app(embedding_provider=local)
    async with app.router.lifespan_context(app):
        assert local.runtime is None and local.task is None
    with pytest.raises(ExplorationError, match="batch or byte limit"):
        await local.encode_documents(["x"] * 9)
    with pytest.raises(ExplorationError, match="local model weights"):
        await local.encode_queries(["file reading"])
    assert local.runtime is None
    fake = FakeProvider()
    assert await fake.encode_documents(["read_file", "add"]) == [
        point(5, 0),
        point(-1, 0),
    ]


async def seed(
    sessions: async_sessionmaker[AsyncSession],
    corpus: dict[str, str],
    *,
    snapshot_id: UUID | None = None,
) -> UUID:
    async with sessions.begin() as session:
        repository = Repository(owner="sample", name=f"vector-{uuid4().hex}")
        session.add(repository)
        await session.flush()
        snapshot = RepositorySnapshot(
            id=snapshot_id or uuid4(),
            repository_id=repository.id,
            commit_sha=SHA,
            ingestion_state=IngestionState.COMPLETED,
        )
        session.add(snapshot)
        await session.flush()
        session.add_all(
            SourceFile(
                snapshot_id=snapshot.id,
                path=path,
                language="python",
                content=content,
                line_count=len(content.splitlines()),
                content_sha256=sha256(content.encode()).hexdigest(),
            )
            for path, content in corpus.items()
        )
        return snapshot.id


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_exact_cosine_rank_and_immutable_evidence(
    migrated_database: Settings,
) -> None:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    try:
        snapshot = await seed(sessions, CORPUS)
        other = await seed(sessions, {"outside.py": "read_file = 9\n"})
        fake = FakeProvider()
        for id_ in (snapshot, other):
            await build_index(sessions, id_)
            await vector.build_vector_index(sessions, id_, fake)
        assert (await vector.build_vector_index(sessions, snapshot, fake)).reused
        app = create_app(migrated_database, embedding_provider=fake)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as api,
        ):
            root = f"/api/v1/snapshots/{snapshot}"
            response = await api.get(
                f"{root}/search/vector", params={"q": "read from disk"}
            )
            assert response.status_code == 200, response.text
            payload = vector.VectorResponse.model_validate(response.json())
            assert payload.model == SYNTHETIC and payload.metric == "cosine_similarity"
            assert (
                payload.commit_sha == SHA
                and payload.vector_version == vector.VECTOR_VERSION
            )
            hits = payload.results
            assert [hit.path for hit in hits] == ["a.py", SPECIAL, "near.py", "far.py"]
            assert [hit.score for hit in hits] == pytest.approx([1, 1, 0.6, -1])
            assert [hit.rank for hit in hits] == [1, 2, 3, 4]
            assert (
                await api.get(f"{root}/search/vector", params={"q": "read from disk"})
            ).json() == response.json()
            assert (
                len(
                    (
                        await api.get(
                            f"{root}/search/vector", params={"q": "read", "limit": 1}
                        )
                    ).json()["results"]
                )
                == 1
            )
            assert (
                await api.get(f"{root}/search/lexical", params={"q": "read_file"})
            ).status_code == 200
            source = await api.get(f"{root}/source", params={"path": SPECIAL})
            assert source.json()["permalink"] == hits[1].permalink
        async with sessions() as session:
            for hit in hits:
                chunk = await session.get_one(SourceChunk, hit.chunk_id)
                assert hit.snapshot_id == chunk.snapshot_id == snapshot
                assert hit.text == chunk.content == CORPUS[hit.path]
                assert (
                    hit.content_sha256
                    == chunk.content_sha256
                    == sha256(hit.text.encode()).hexdigest()
                )
                assert hit.source_sha256 == chunk.source_sha256
                assert (hit.start_line, hit.end_line) == (1, 1)
        assert hits[1].permalink.endswith(f"/blob/{SHA}/src/%C3%A9%20%23%25.py#L1")
        print(
            json.dumps(
                {"synthetic": [[hit.path, hit.score] for hit in hits]},
                ensure_ascii=False,
            )
        )
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_concurrent_publication_and_batch_limits(
    migrated_database: Settings,
) -> None:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    try:
        snapshot = await seed(
            sessions, {f"file{i}.py": f"n = {i}\n" for i in range(11)}
        )
        await build_index(sessions, snapshot)
        delayed = FakeProvider()
        delayed.release = asyncio.Event()
        winner = FakeProvider()
        async with asyncio.timeout(10), asyncio.TaskGroup() as tasks:
            first = tasks.create_task(
                vector.build_vector_index(sessions, snapshot, delayed)
            )
            try:
                await delayed.entered.wait()
                async with sessions() as session:
                    assert await session.get(VectorIndex, snapshot) is None
                    assert (
                        await session.scalar(
                            select(func.count())
                            .select_from(ChunkEmbedding)
                            .where(ChunkEmbedding.snapshot_id == snapshot)
                        )
                        == 0
                    )
                second = await vector.build_vector_index(sessions, snapshot, winner)
            finally:
                delayed.release.set()
        assert not second.reused and first.result().reused
        assert delayed.batches == winner.batches == [8, 3]
        assert second.chunk_count == 11
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_rollback_and_cross_snapshot_or_version_constraints(
    migrated_database: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    try:
        snapshot = await seed(sessions, CORPUS)
        other = await seed(sessions, CORPUS)
        for id_ in (snapshot, other):
            await build_index(sessions, id_)
        async with sessions() as session:
            foreign = await session.scalar(
                select(SourceChunk.id).where(SourceChunk.snapshot_id == other).limit(1)
            )
            assert foreign is not None

        original = ChunkEmbedding

        def corrupted(**kwargs: object) -> ChunkEmbedding:
            return original(**(kwargs | {"chunk_id": foreign}))

        with monkeypatch.context() as patch:
            patch.setattr(vector, "ChunkEmbedding", corrupted)
            with pytest.raises(IntegrityError):
                await vector.build_vector_index(sessions, snapshot, FakeProvider())
        async with sessions() as session:
            assert await session.get(VectorIndex, snapshot) is None
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(ChunkEmbedding)
                    .where(ChunkEmbedding.snapshot_id == snapshot)
                )
                == 0
            )
        await vector.build_vector_index(sessions, snapshot, FakeProvider())
        for version, chunking in [
            (vector.VECTOR_VERSION, VERSION),
            ("wrong-version", VERSION),
            (vector.VECTOR_VERSION, "wrong-chunking"),
        ]:
            with pytest.raises(IntegrityError) as error:
                async with sessions.begin() as session:
                    session.add(
                        ChunkEmbedding(
                            snapshot_id=snapshot,
                            chunk_id=foreign,
                            chunking_version=chunking,
                            vector_version=version,
                            embedding=point(1, 0),
                        )
                    )
            assert getattr(error.value.orig, "sqlstate", None) == "23503"
        with pytest.raises(ExplorationError, match="different version or model"):
            await vector.build_vector_index(sessions, snapshot, FakeProvider(MODEL))
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_empty_indexes_missing_provider_and_invalid_requests(
    migrated_database: Settings,
    tmp_path: Path,
) -> None:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    try:
        empty = await seed(sessions, {"empty.py": ""})
        unindexed = await seed(sessions, CORPUS)
        built = await seed(sessions, CORPUS)
        fake = FakeProvider(MODEL)
        with pytest.raises(ExplorationError, match="lexical index"):
            await vector.build_vector_index(sessions, unindexed, fake)
        await build_index(sessions, empty)
        assert (await vector.build_vector_index(sessions, empty, fake)).chunk_count == 0
        assert not fake.batches
        await build_index(sessions, built)
        await vector.build_vector_index(sessions, built, fake)
        local = LocalOnnxProvider(tmp_path)
        app = create_app(migrated_database, embedding_provider=local)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as api,
        ):
            assert local.task is None
            assert (
                await api.get(
                    f"/api/v1/snapshots/{empty}/search/vector", params={"q": "hello"}
                )
            ).json()["results"] == []
            assert local.task is None
            for id_, status, code in [
                (unindexed, 409, "vector_index_unavailable"),
                (uuid4(), 404, "snapshot_not_found"),
                (built, 503, "embedding_unavailable"),
            ]:
                response = await api.get(
                    f"/api/v1/snapshots/{id_}/search/vector",
                    params={"q": "hello"},
                    headers={"X-Request-ID": "vector-errors"},
                )
                assert response.status_code == status, response.text
                assert response.json()["error"]["code"] == code
                assert response.json()["error"]["request_id"] == "vector-errors"
            for params in [{"q": " "}, {"q": "a" * 513}, {"q": "x", "limit": "31"}]:
                assert (
                    await api.get(
                        f"/api/v1/snapshots/{built}/search/vector", params=params
                    )
                ).status_code == 422
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change", "code"),
    [
        ("removed", "vector_index_changed"),
        ("model_revision", "vector_index_incompatible"),
    ],
)
async def test_search_revalidates_after_paused_inference(
    migrated_database: Settings,
    change: str,
    code: str,
) -> None:
    class PausedQuery(FakeProvider):
        async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
            entered.set()
            await release.wait()
            return await super().encode_queries(texts)

    entered, release = asyncio.Event(), asyncio.Event()
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    try:
        snapshot = await seed(sessions, CORPUS)
        await build_index(sessions, snapshot)
        await vector.build_vector_index(sessions, snapshot, FakeProvider())
        async with (
            sessions() as reader,
            asyncio.timeout(10),
            asyncio.TaskGroup() as group,
        ):

            async def search() -> None:
                with pytest.raises(ExplorationError) as error:
                    await vector.vector_search(
                        reader, snapshot, "read file", 10, PausedQuery()
                    )
                assert (error.value.status, error.value.code) == (409, code)

            lookup = group.create_task(search())
            try:
                await entered.wait()
                assert not reader.in_transaction()
                async with sessions.begin() as writer:
                    if change == "removed":
                        await writer.execute(
                            delete(VectorIndex).where(
                                VectorIndex.snapshot_id == snapshot
                            )
                        )
                    else:
                        await writer.execute(
                            update(VectorIndex)
                            .where(VectorIndex.snapshot_id == snapshot)
                            .values(model_revision="different")
                        )
            finally:
                release.set()
            await lookup
    finally:
        await engine.dispose()
