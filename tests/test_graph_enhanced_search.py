import asyncio
from collections.abc import Sequence
from datetime import timedelta
from fractions import Fraction
from hashlib import sha256
from uuid import UUID

import httpx
import pytest
from sqlalchemy import select, update
from test_hybrid_search import HybridProvider, candidate
from test_vector_retrieval import SHA, point, seed

from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.database.models import GraphAnalysis, GraphNode, SearchIndex
from repobrain.graph.exploration import ExplorationError
from repobrain.graph.service import analyze_snapshot
from repobrain.main import create_app
from repobrain.search import graph_enhanced as graph
from repobrain.search.hybrid import fuse
from repobrain.search.service import build_index
from repobrain.search.vector import build_vector_index
from repobrain.settings import Settings


class GraphProvider(HybridProvider):
    async def encode_documents(self, texts: Sequence[str]) -> list[list[float]]:
        return [
            point(-1 if "dependency" in text and "read_file" not in text else 1, 0)
            for text in texts
        ]

    async def encode_queries(self, texts: Sequence[str]) -> list[list[float]]:
        await super().encode_queries(texts)
        return [point(1, 0) for _ in texts]


def test_graph_score_decay_and_deduplication() -> None:
    base = candidate("seed.py", 1)
    seed_hit = fuse([base], [base], 1)[0]
    one = graph.PathEdge(
        edge_id=UUID(int=1),
        source_node_id=UUID(int=2),
        target_node_id=UUID(int=3),
        relationship="CONTAINS",
    )
    two = graph.PathEdge(
        edge_id=UUID(int=4),
        source_node_id=one.target_node_id,
        target_node_id=UUID(int=5),
        relationship="IMPORTS",
    )
    path = graph.Walk(
        seed_hit,
        (one.source_node_id, one.target_node_id, two.target_node_id),
        (one, two),
    )
    hit = graph.rank_results([seed_hit], {base.match.chunk_id: (base.match, path)}, 10)[
        0
    ]
    assert hit.hybrid_score == float(Fraction(2, 61))
    assert hit.graph_contribution == float(Fraction(3, 244))
    assert hit.score == float(Fraction(2, 61) + Fraction(3, 244))
    assert hit.provenance is not None and hit.provenance.hop_count == 2
    assert hit.channels == ["lexical", "vector", "graph"]


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_graph_search_discovers_dependency_and_preserves_evidence(
    migrated_database: Settings,
) -> None:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    fake = GraphProvider()
    dependency = '"""dependency"""\ndef helper():\r\n    return \'dependency\'\r\n'
    corpus = {
        "a.py": "from z_dependency import helper as read_file\nimport x_bridge\n",
        "z_dependency.py": dependency,
        "x_bridge.py": "import tail  # dependency\nimport a\n",
        "tail.py": "import end  # dependency\n",
        "end.py": "result = 'dependency'\n",
        "broken.py": "def invalid(  # dependency\n",
        **{f"filler_{i:02}.py": "pass\n" for i in range(32)},
    }
    try:
        snapshot = await seed(sessions, corpus)
        other = await seed(sessions, {"z_dependency.py": "private_fixture = 1\n"})
        await analyze_snapshot(sessions, other)
        await build_index(sessions, snapshot)
        await build_vector_index(sessions, snapshot, fake)
        app = create_app(migrated_database, embedding_provider=fake)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as api,
        ):
            root = f"/api/v1/snapshots/{snapshot}/search"
            params = {"q": "read_file", "limit": "30"}
            response = await api.get(f"{root}/graph-enhanced", params=params)
            assert response.status_code == 409 and response.headers["x-request-id"]
            assert fake.query_count == 0
            await analyze_snapshot(sessions, snapshot)
            baseline = await api.get(f"{root}/hybrid", params=params)
            assert baseline.status_code == 200
            assert "z_dependency.py" not in {
                hit["path"] for hit in baseline.json()["results"]
            }
            query_count = fake.query_count
            response = await api.get(f"{root}/graph-enhanced", params=params)
            assert response.status_code == 200, response.text
            assert fake.query_count == query_count + 1
            payload = graph.GraphSearchResponse.model_validate(response.json())
            assert payload.commit_sha == SHA and payload.snapshot_id == snapshot
            assert [hit.path for hit in payload.results[:4]] == [
                "a.py",
                "x_bridge.py",
                "z_dependency.py",
                "z_dependency.py",
            ]
            assert payload.traversal.depth_reached == 2
            assert payload.traversal.depth_limit_reached
            assert payload.traversal.truncated
            assert payload.traversal.visited_nodes == 9
            assert payload.traversal.traversed_edges == 6
            assert payload.results[0].score == float(Fraction(2, 61))
            module, symbol = payload.results[2:4]
            for hit, relationship, fragment in (
                (module, "IMPORTS", "L1"),
                (symbol, "IMPORTS_SYMBOL", "L2-L3"),
            ):
                assert hit.hybrid_rank is None and hit.hybrid_score is None
                assert hit.graph_contribution == hit.score == float(Fraction(3, 122))
                assert hit.channels == ["graph"]
                assert hit.provenance is not None
                assert hit.provenance.seed_rank == hit.provenance.hop_count == 1
                assert hit.provenance.seed_chunk_id == payload.results[0].chunk_id
                edge = hit.provenance.edges[0]
                assert edge.relationship == relationship
                assert hit.provenance.node_ids == (
                    edge.source_node_id,
                    edge.target_node_id,
                )
                assert hit.source_sha256 == sha256(dependency.encode()).hexdigest()
                assert hit.content_sha256 == sha256(hit.text.encode()).hexdigest()
                assert hit.permalink == (
                    f"https://github.com/{payload.repository}/blob/{SHA}/"
                    f"z_dependency.py#{fragment}"
                )
            assert module.text == '"""dependency"""\n'
            assert symbol.text == "def helper():\r\n    return 'dependency'\r\n"
            tail = next(hit for hit in payload.results if hit.path == "tail.py")
            assert tail.graph_contribution == float(Fraction(3, 244))
            assert tail.provenance is not None and tail.provenance.hop_count == 2
            assert [edge.relationship for edge in tail.provenance.edges] == [
                "IMPORTS",
                "IMPORTS",
            ]
            assert len({hit.chunk_id for hit in payload.results}) == len(
                payload.results
            )
            assert (
                await api.get(f"{root}/graph-enhanced", params=params)
            ).json() == response.json()
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_nested_span_and_high_degree_containment(
    migrated_database: Settings,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    fake = GraphProvider()
    content = "def outer():\n    def nested():\n        return 'nested'\n"
    wide = "graph_wide = 1\n" + "".join(
        f"def leaf_{i:02}():\n    return {i}\n" for i in range(60)
    )
    try:
        snapshot = await seed(sessions, {"nested.py": content, "wide.py": wide})
        await analyze_snapshot(sessions, snapshot)
        await build_index(sessions, snapshot)
        await build_vector_index(sessions, snapshot, fake)
        async with sessions() as session:
            result = await graph.graph_search(session, snapshot, "graph_wide", 30, fake)
            assert result.traversal.visited_nodes <= 50
            assert result.traversal.traversed_edges <= 100
            assert (
                result.traversal.node_limit_reached
                and result.traversal.chunk_limit_reached
            )
            assert result.traversal.expanded_chunks == 30
            assert any(
                hit.provenance and hit.provenance.edges[0].relationship == "CONTAINS"
                for hit in result.results
            )
        async with sessions() as session:
            result = await graph.graph_search(session, snapshot, "nested", 1, fake)
            assert result.results[0].path == "nested.py"
            # The complete function chunk has more overlap with outer than nested.
            starts = await graph.seed_nodes(
                session,
                snapshot,
                [
                    fuse([candidate("nested.py", 1)], [], 1)[0].model_copy(
                        update={"chunk_id": result.results[0].chunk_id}
                    )
                ],
            )
            node = await session.scalar(
                select(GraphNode).where(
                    GraphNode.snapshot_id == snapshot,
                    GraphNode.id == starts[result.results[0].chunk_id],
                )
            )
            assert node is not None and node.qualified_name.endswith("outer")
        with monkeypatch.context() as policy:
            policy.setattr(graph, "MAX_EDGES", 6)
            async with sessions() as session:
                limited = await graph.graph_search(
                    session, snapshot, "graph_wide", 30, fake
                )
                assert limited.traversal.edge_limit_reached
                assert limited.traversal.traversed_edges == 6
                assert limited.traversal.truncated
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["graph", "index"])
async def test_graph_prerequisites_and_revalidation(
    migrated_database: Settings, change: str
) -> None:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    fake = GraphProvider()
    try:
        snapshot = await seed(sessions, {"one.py": "def broken(\n"})
        await analyze_snapshot(sessions, snapshot)
        async with sessions() as reader:
            with pytest.raises(ExplorationError) as missing:
                await graph.graph_search(reader, snapshot, "broken", 1, fake)
            assert missing.value.code == "search_index_unavailable"
        await build_index(sessions, snapshot)
        await build_vector_index(sessions, snapshot, fake)
        assert fake.query_count == 0
        async with sessions() as reader:
            result = await graph.graph_search(reader, snapshot, "broken", 1, fake)
            assert result.results[0].path == "one.py"
            assert result.traversal.expanded_chunks == 0
        empty = await seed(sessions, {})
        await analyze_snapshot(sessions, empty)
        await build_index(sessions, empty)
        await build_vector_index(sessions, empty, fake)
        async with sessions() as reader:
            assert (
                await graph.graph_search(reader, empty, "broken", 1, fake)
            ).results == []
        fake.entered.clear()
        fake.release = asyncio.Event()
        async with (
            asyncio.timeout(10),
            sessions() as reader,
            asyncio.TaskGroup() as group,
        ):

            async def search_during_change() -> None:
                with pytest.raises(ExplorationError) as caught:
                    await graph.graph_search(reader, snapshot, "broken", 1, fake)
                assert caught.value.status == 409
                assert caught.value.code == (
                    "graph_analysis_changed"
                    if change == "graph"
                    else "hybrid_indexes_changed"
                )

            group.create_task(search_during_change())
            await fake.entered.wait()
            assert not reader.in_transaction()
            async with sessions.begin() as writer:
                if change == "graph":
                    await writer.execute(
                        update(GraphAnalysis)
                        .where(GraphAnalysis.snapshot_id == snapshot)
                        .values(analyzed_files=GraphAnalysis.analyzed_files)
                    )
                else:
                    await writer.execute(
                        update(SearchIndex)
                        .where(SearchIndex.snapshot_id == snapshot)
                        .values(built_at=SearchIndex.built_at + timedelta(seconds=1))
                    )
            fake.release.set()
        assert fake.query_count == 2
    finally:
        await engine.dispose()
