import asyncio
from collections.abc import Sequence
from dataclasses import replace
from fractions import Fraction
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import delete, func, update
from test_vector_retrieval import CORPUS, SHA, SPECIAL, FakeProvider, point, seed

from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.database.models import SearchIndex, VectorIndex
from repobrain.graph.exploration import ExplorationError
from repobrain.main import create_app
from repobrain.search.embedding import unavailable
from repobrain.search.hybrid import FusionPolicy, HybridResponse, fuse, hybrid_search
from repobrain.search.service import Candidate, Match, build_index
from repobrain.search.vector import build_vector_index
from repobrain.settings import Settings


def candidate(path: str, rank: int, *, line: int = 1, key: str = "") -> Candidate:
    return Candidate(
        Match(
            snapshot_id=uuid4(),
            repository="sample/code",
            commit_sha=SHA,
            chunk_id=uuid4(),
            source_file_id=uuid4(),
            path=path,
            start_line=line,
            end_line=line,
            text="pass",
            source_sha256="",
            content_sha256="",
            rank=rank,
            score=-0.25,
            permalink="",
        ),
        key,
    )


def test_fuse_rank_only_and_deduplicates() -> None:
    shared = candidate("shared.py", 2)
    shared_vector = replace(
        shared, match=shared.match.model_copy(update={"rank": 3, "score": 0.8})
    )
    lexical_only = candidate("z.py", 1)
    vector_only = candidate("a.py", 1)
    lexical = [lexical_only, shared, shared_vector]
    vector = [vector_only, shared_vector]
    hits = fuse(lexical, vector, 30)
    assert FusionPolicy().k == 60
    assert [hit.path for hit in hits] == ["shared.py", "a.py", "z.py"]
    assert [hit.rank for hit in hits] == [1, 2, 3]
    assert hits[0].score == float(Fraction(1, 62) + Fraction(1, 63))
    assert hits[0].channels == ["lexical", "vector"]
    assert (hits[0].lexical_rank, hits[0].lexical_score) == (2, -0.25)
    assert (hits[0].vector_rank, hits[0].vector_score) == (3, 0.8)
    assert hits[1].lexical_rank is None and hits[1].channels == ["vector"]
    assert hits[2].vector_rank is None and hits[2].channels == ["lexical"]
    assert fuse(lexical, vector, 1) == hits[:1]
    assert fuse(lexical, [], 1)[0].score == fuse([], vector, 1)[0].score == 1 / 61
    assert fuse([], [], 30) == []


@pytest.mark.parametrize(
    ("lines", "keys"), [((2, 1), ("a", "z")), ((1, 1), ("z", "a"))]
)
def test_fused_ties_use_line_then_stable_key(
    lines: tuple[int, int], keys: tuple[str, str]
) -> None:
    first = candidate("same.py", 1, line=lines[0], key=keys[0])
    second = candidate("same.py", 1, line=lines[1], key=keys[1])
    assert fuse([first], [second], 1)[0].chunk_id == second.match.chunk_id


class HybridProvider(FakeProvider):
    query_count = 0
    fail = False

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        self.query_count += 1
        self.entered.set()
        if self.release is not None:
            await self.release.wait()
        if self.fail:
            raise unavailable("Fixture embedding unavailable")
        return [point(-2, 0) for _ in texts]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_hybrid_api_ranking_and_evidence(migrated_database: Settings) -> None:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    fake = HybridProvider()
    try:
        snapshot = await seed(sessions, CORPUS)
        other = await seed(
            sessions, {f"outside_{i:02}.py": "read_file = 77\n" for i in range(32)}
        )
        empty = await seed(sessions, {})
        for snapshot_id in (snapshot, other, empty):
            await build_index(sessions, snapshot_id)
            await build_vector_index(sessions, snapshot_id, fake)
        app = create_app(migrated_database, embedding_provider=fake)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as api,
        ):
            assert fake.query_count == 0
            root = f"/api/v1/snapshots/{snapshot}/search"
            params = {"q": "read_file"}
            response = await api.get(f"{root}/hybrid", params=params)
            assert response.status_code == 200, response.text
            assert response.headers["x-request-id"]
            assert fake.query_count == 1
            payload = HybridResponse.model_validate(response.json())
            assert payload.snapshot_id == snapshot and payload.commit_sha == SHA
            assert payload.model == fake.model and payload.fusion == FusionPolicy()
            assert [hit.path for hit in payload.results] == [
                "a.py",
                SPECIAL,
                "far.py",
                "near.py",
            ]
            baselines = {}
            for channel in ("lexical", "vector"):
                baseline = await api.get(f"{root}/{channel}", params=params)
                assert baseline.status_code == 200, baseline.text
                baselines[channel] = {
                    hit["chunk_id"]: hit for hit in baseline.json()["results"]
                }
            assert list(baselines["vector"].values())[0]["path"] == "far.py"
            for hit in payload.results:
                combined = Fraction()
                for channel in ("lexical", "vector"):
                    baseline_hit = baselines[channel].get(str(hit.chunk_id))
                    if baseline_hit is None:
                        assert channel not in hit.channels
                        continue
                    assert channel in hit.channels
                    assert getattr(hit, f"{channel}_rank") == baseline_hit["rank"]
                    assert getattr(hit, f"{channel}_score") == baseline_hit["score"]
                    combined += Fraction(1, 60 + baseline_hit["rank"])
                    assert hit.model_dump(
                        mode="json", include=set(Match.model_fields) - {"rank", "score"}
                    ) == {
                        key: value
                        for key, value in baseline_hit.items()
                        if key not in {"rank", "score"}
                    }
                assert hit.score == float(combined)
                assert hit.text == CORPUS[hit.path]
                assert f"/blob/{SHA}/" in hit.permalink
            assert (
                await api.get(f"{root}/hybrid", params=params)
            ).json() == response.json()
            assert (
                await api.get(f"{root}/hybrid", params={**params, "limit": 1})
            ).json()["results"] == response.json()["results"][:1]
            vector_only = (
                await api.get(f"{root}/hybrid", params={"q": "unmatched"})
            ).json()["results"]
            assert len(vector_only) == 4
            assert vector_only[0]["channels"] == ["vector"]
            assert vector_only[0]["score"] == 1 / 61
            capped = await api.get(
                f"/api/v1/snapshots/{other}/search/hybrid",
                params={**params, "limit": 30},
            )
            assert capped.status_code == 200
            capped_hits = HybridResponse.model_validate(capped.json()).results
            assert [hit.path for hit in capped_hits] == [
                f"outside_{i:02}.py" for i in range(30)
            ]
            assert capped_hits[-1].lexical_rank == capped_hits[-1].vector_rank == 30
            assert capped_hits[-1].score == 2 / 90
            count = fake.query_count
            for bad_params in (
                {"q": ""},
                {"q": "!!"},
                {"q": "a" * 257},
                {**params, "limit": "31"},
            ):
                assert (
                    await api.get(f"{root}/hybrid", params=bad_params)
                ).status_code == 422
            empty_response = await api.get(
                f"/api/v1/snapshots/{empty}/search/hybrid", params=params
            )
            assert empty_response.status_code == 200
            assert empty_response.json()["results"] == []
            assert fake.query_count == count
            fake.fail = True
            failure = await api.get(f"{root}/hybrid", params=params)
            assert failure.status_code == 503 and failure.headers["x-request-id"]
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("change", "error"),
    [
        ("remove", "vector_index_unavailable"),
        ("model", "vector_index_incompatible"),
        ("lexical_stamp", "hybrid_indexes_changed"),
    ],
)
async def test_revalidates_after_encoding(
    migrated_database: Settings, change: str, error: str
) -> None:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    fake = HybridProvider()
    try:
        snapshot = await seed(sessions, {"a.py": "read_file = 1\n"})
        async with sessions() as session:
            with pytest.raises(ExplorationError) as caught:
                await hybrid_search(session, snapshot, "read_file", 10, fake)
            assert (caught.value.status, caught.value.code) == (
                409,
                "search_index_unavailable",
            )
        await build_index(sessions, snapshot)
        async with sessions() as session:
            with pytest.raises(ExplorationError) as caught:
                await hybrid_search(session, snapshot, "read_file", 10, fake)
            assert (caught.value.status, caught.value.code) == (
                409,
                "vector_index_unavailable",
            )
        assert fake.query_count == 0
        await build_vector_index(sessions, snapshot, fake)
        fake.entered.clear()
        fake.release = asyncio.Event()
        async with (
            asyncio.timeout(10),
            sessions() as reader,
            asyncio.TaskGroup() as group,
        ):

            async def search_during_change() -> None:
                with pytest.raises(ExplorationError) as caught:
                    await hybrid_search(reader, snapshot, "read_file", 10, fake)
                assert (caught.value.status, caught.value.code) == (409, error)

            group.create_task(search_during_change())
            await fake.entered.wait()
            assert not reader.in_transaction()
            async with sessions.begin() as writer:
                if change == "remove":
                    await writer.execute(
                        delete(VectorIndex).where(VectorIndex.snapshot_id == snapshot)
                    )
                elif change == "model":
                    await writer.execute(
                        update(VectorIndex)
                        .where(VectorIndex.snapshot_id == snapshot)
                        .values(model_revision="mutated")
                    )
                else:
                    await writer.execute(
                        update(SearchIndex)
                        .where(SearchIndex.snapshot_id == snapshot)
                        .values(built_at=func.clock_timestamp())
                    )
            fake.release.set()
        assert fake.query_count == 1
    finally:
        await engine.dispose()
