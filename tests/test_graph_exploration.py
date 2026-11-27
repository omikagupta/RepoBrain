from collections.abc import AsyncIterator
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID, uuid4

import httpx
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.database.models import (
    GraphAnalysis,
    GraphEdge,
    GraphNode,
    IngestionState,
    Repository,
    RepositorySnapshot,
    SourceFile,
)
from repobrain.graph.exploration import ExplorationError, slice_source
from repobrain.main import create_app
from repobrain.settings import Settings

SPECIAL_PATH = "pkg/é #?%.py"
SPECIAL_TEXT = "first\r\nsecond\rthird\nfourth"
COMMIT = "a" * 40


@pytest.mark.parametrize("separator", ["\n", "\r\n", "\r"])
def test_slice_preserves_blank_lines_and_ignores_terminal_separator(
    separator: str,
) -> None:
    result = slice_source(separator.join(["one", "", "three", ""]), 2, 99)
    assert [(line.line_number, line.text) for line in result] == [(2, ""), (3, "three")]


def test_source_window_bounds_serialized_text() -> None:
    with pytest.raises(ExplorationError, match="byte limit"):
        slice_source("\t" * 40_000, 1, 1)


@dataclass
class Fixture:
    api: httpx.AsyncClient
    sessions: async_sessionmaker[AsyncSession]
    snapshot: UUID
    empty: UUID
    unanalyzed: UUID
    nodes: list[UUID]

    def url(self, resource: str, snapshot: UUID | None = None) -> str:
        return f"/api/v1/snapshots/{snapshot or self.snapshot}/{resource}"


def edge(snapshot: UUID, index: int, source: UUID, target: UUID) -> GraphEdge:
    return GraphEdge(
        id=uuid4(),
        snapshot_id=snapshot,
        source_id=source,
        target_id=target,
        stable_key=f"{index:064x}",
        relationship="IMPORTS",
        line=index + 1,
        column=2,
        provenance="fixture",
    )


@pytest_asyncio.fixture
async def graph_api(migrated_database: Settings) -> AsyncIterator[Fixture]:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    try:
        snapshot, empty, unanalyzed = uuid4(), uuid4(), uuid4()
        nodes = [uuid4() for _ in range(5)]
        async with sessions.begin() as session:
            repository = Repository(owner="sample", name=f"api-{uuid4().hex}")
            session.add(repository)
            await session.flush()
            for id_, sha in [
                (snapshot, COMMIT),
                (empty, "b" * 40),
                (unanalyzed, "c" * 40),
            ]:
                session.add(
                    RepositorySnapshot(
                        id=id_,
                        repository_id=repository.id,
                        commit_sha=sha,
                        ingestion_state=IngestionState.COMPLETED,
                    )
                )
            await session.flush()
            session.add_all(
                [
                    GraphAnalysis(
                        snapshot_id=snapshot,
                        analyzed_files=2,
                        node_count=5,
                        edge_count=4,
                        diagnostics=[{"code": "fixture"}],
                    ),
                    GraphAnalysis(
                        snapshot_id=empty,
                        analyzed_files=0,
                        node_count=0,
                        edge_count=0,
                        diagnostics=[],
                    ),
                ]
            )
            files = sorted(
                [
                    (snapshot, SPECIAL_PATH, SPECIAL_TEXT),
                    (snapshot, "empty.py", ""),
                    (unanalyzed, "before-graph.py", "stored"),
                ],
                key=lambda file: file[1],
            )
            for owner, path, content in files:
                session.add(
                    SourceFile(
                        snapshot_id=owner,
                        path=path,
                        language="python",
                        content=content,
                        content_sha256=sha256(content.encode()).hexdigest(),
                        line_count=len(content.splitlines()),
                    )
                )
            await session.flush()
            file_id = await session.scalar(
                select(SourceFile.id).where(
                    SourceFile.snapshot_id == snapshot, SourceFile.path == SPECIAL_PATH
                )
            )
            assert file_id is not None
            for index, id_ in enumerate(nodes):
                session.add(
                    GraphNode(
                        id=id_,
                        snapshot_id=snapshot,
                        source_file_id=file_id,
                        stable_key=f"{index:064x}",
                        kind="module" if index == 0 else "function",
                        qualified_name="pkg" if index == 0 else f"pkg.fun{index}",
                        start_line=1,
                        end_line=4,
                        is_async=index == 1,
                    )
                )
            await session.flush()
            for index, (source, target) in enumerate([(0, 1), (1, 2), (2, 0), (3, 0)]):
                session.add(edge(snapshot, index, nodes[source], nodes[target]))
        app = create_app(migrated_database)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as api,
        ):
            yield Fixture(api, sessions, snapshot, empty, unanalyzed, nodes)
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_summary_and_errors(graph_api: Fixture) -> None:
    f = graph_api
    response = await f.api.get(f.url("graph"))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["commit_sha"] == COMMIT and body["repository"].startswith("sample/api-")
    assert [
        body[key]
        for key in ("analyzed_files", "node_count", "edge_count", "diagnostic_count")
    ] == [2, 5, 4, 1]
    assert (await f.api.get(f.url("graph", f.empty))).json()["node_count"] == 0
    assert (await f.api.get(f.url("edges", f.empty))).json() == {
        "items": [],
        "next_cursor": None,
    }
    absent = await f.api.get(
        f.url("graph", f.unanalyzed), headers={"X-Request-ID": "graph-check"}
    )
    assert absent.status_code == 409
    assert absent.json()["error"]["code"] == "graph_not_analyzed"
    assert (
        absent.json()["error"]["request_id"]
        == absent.headers["X-Request-ID"]
        == "graph-check"
    )
    assert (await f.api.get(f.url("nodes", uuid4()))).status_code == 404
    assert (await f.api.get("/api/v1/snapshots/invalid/nodes")).status_code == 422
    assert (
        await f.api.get(f.url("neighborhood"), params={"node_id": "invalid"})
    ).status_code == 422


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_node_pages_and_cursor_context(graph_api: Fixture) -> None:
    f = graph_api
    query = {
        "kind": "function",
        "qualified_name_prefix": "pkg.fun",
        "path": SPECIAL_PATH,
    }
    first = await f.api.get(f.url("nodes"), params={**query, "limit": 2})
    assert first.status_code == 200, first.text
    page = first.json()
    cursor = page["next_cursor"]
    second = await f.api.get(
        f.url("nodes"), params={**query, "limit": 3, "cursor": cursor}
    )
    assert second.status_code == 200, second.text
    items = page["items"] + second.json()["items"]
    assert [item["id"] for item in items] == [str(id_) for id_ in f.nodes[1:]]
    assert items[0]["is_async"] and items[0]["path"] == SPECIAL_PATH
    assert second.json()["next_cursor"] is None
    for request in (
        f.api.get(
            f.url("nodes"),
            params={
                **query,
                "cursor": cursor[:-1] + ("a" if cursor[-1] != "a" else "b"),
            },
        ),
        f.api.get(f.url("nodes"), params={"cursor": cursor}),
        f.api.get(f.url("nodes", f.empty), params={**query, "cursor": cursor}),
        f.api.get(f.url("edges"), params={"cursor": cursor}),
    ):
        response = await request
        assert response.status_code == 422
        assert response.json()["error"]["code"] == "invalid_cursor"
    literal = await f.api.get(f.url("nodes"), params={"qualified_name_prefix": "pkg.%"})
    assert literal.json()["items"] == []


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_edge_filters_and_traversal(graph_api: Fixture) -> None:
    f = graph_api
    center = str(f.nodes[0])
    for field, count in [("source_id", 1), ("target_id", 2)]:
        response = await f.api.get(
            f.url("edges"), params={field: center, "relationship": "IMPORTS"}
        )
        assert len(response.json()["items"]) == count
        assert all(
            item[field] == center and item["column"] == 2
            for item in response.json()["items"]
        )
    all_edges: list[str] = []
    params: dict[str, str | int] = {"limit": 1}
    for _ in range(4):
        page = (await f.api.get(f.url("edges"), params=params)).json()
        all_edges.extend(item["id"] for item in page["items"])
        if page["next_cursor"] is None:
            break
        params["cursor"] = page["next_cursor"]
    assert page["next_cursor"] is None and len(all_edges) == len(set(all_edges)) == 4
    for direction, depth, included, count in [
        ("outgoing", 1, [0, 1], 1),
        ("outgoing", 2, [0, 1, 2], 2),
        ("incoming", 1, [0, 2, 3], 2),
        ("both", 2, [0, 1, 2, 3], 4),
    ]:
        response = await f.api.get(
            f.url("neighborhood"),
            params={
                "node_id": center,
                "direction": direction,
                "depth": depth,
            },
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert [node["id"] for node in body["nodes"]] == [
            str(f.nodes[i]) for i in included
        ]
        assert (
            len(body["edges"]) == count
            and len({e["id"] for e in body["edges"]}) == count
        )
        assert not body["truncated"]
    excluded = await f.api.get(
        f.url("neighborhood"),
        params={
            "node_id": center,
            "relationship": "CONTAINS",
        },
    )
    assert excluded.json()["edges"] == []
    assert (
        await f.api.get(f.url("neighborhood", f.empty), params={"node_id": center})
    ).status_code == 404


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_source_evidence_and_read_only(graph_api: Fixture) -> None:
    f = graph_api
    async with f.sessions() as session:
        before = await session.get_one(RepositorySnapshot, f.snapshot)
    subject = f.url("source")
    response = await f.api.get(
        subject, params={"path": SPECIAL_PATH, "start_line": 2, "end_line": 3}
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["lines"] == [
        {"line_number": 2, "text": "second"},
        {"line_number": 3, "text": "third"},
    ]
    assert body["permalink"] == (
        f"https://github.com/{body['repository']}/blob/{COMMIT}/pkg/%C3%A9%20%23%3F%25.py#L2-L3"
    )
    assert (
        body["actual_range"]
        == body["requested_range"]
        == {"start_line": 2, "end_line": 3}
    )
    assert body["content_sha256"] == sha256(SPECIAL_TEXT.encode()).hexdigest()
    empty = (await f.api.get(subject, params={"path": "empty.py"})).json()
    assert empty["lines"] == [] and empty["actual_range"] == {
        "start_line": None,
        "end_line": None,
    }
    assert empty["permalink"].endswith("/empty.py")
    assert (await f.api.get(subject, params={"path": "missing.py"})).status_code == 404
    assert (await f.api.get(subject, params={"path": "../empty.py"})).status_code == 422
    assert (
        await f.api.get(subject, params={"path": SPECIAL_PATH, "start_line": 5})
    ).status_code == 422
    assert (
        await f.api.get(subject, params={"path": SPECIAL_PATH, "end_line": 201})
    ).status_code == 422
    independent = await f.api.get(
        f.url("source", f.unanalyzed), params={"path": "before-graph.py"}
    )
    assert independent.status_code == 200
    same_path_other_snapshot = await f.api.get(
        f.url("source", f.unanalyzed), params={"path": SPECIAL_PATH}
    )
    assert same_path_other_snapshot.status_code == 404
    async with f.sessions() as session:
        after = await session.get_one(RepositorySnapshot, f.snapshot)
        assert (before.ingestion_state, before.updated_at) == (
            after.ingestion_state,
            after.updated_at,
        )
        assert (await session.get_one(GraphAnalysis, f.snapshot)).node_count == 5
        assert (
            len(
                (
                    await session.scalars(
                        select(GraphNode.id).where(GraphNode.snapshot_id == f.snapshot)
                    )
                ).all()
            )
            == 5
        )
        assert (
            len(
                (
                    await session.scalars(
                        select(GraphEdge.id).where(GraphEdge.snapshot_id == f.snapshot)
                    )
                ).all()
            )
            == 4
        )


@pytest.mark.postgres
@pytest.mark.asyncio
@pytest.mark.parametrize("cap", ["nodes", "edges"])
async def test_neighborhood_honors_caps(graph_api: Fixture, cap: str) -> None:
    f = graph_api
    async with f.sessions.begin() as session:
        file = await session.scalar(
            select(SourceFile.id).where(
                SourceFile.snapshot_id == f.snapshot, SourceFile.path == SPECIAL_PATH
            )
        )
        assert file is not None
        if cap == "nodes":
            targets = [uuid4() for _ in range(105)]
            session.add_all(
                GraphNode(
                    id=id_,
                    snapshot_id=f.snapshot,
                    source_file_id=file,
                    stable_key=f"{index + 1000:064x}",
                    kind="module",
                    qualified_name=f"target{index}",
                    is_async=False,
                )
                for index, id_ in enumerate(targets)
            )
            await session.flush()
        else:
            targets = [f.nodes[1]] * 205
        session.add_all(
            edge(f.snapshot, index + 1000, f.nodes[0], target)
            for index, target in enumerate(targets)
        )
    params: dict[str, str | int] = {
        "node_id": str(f.nodes[0]),
        "direction": "outgoing",
        "depth": 2,
    }
    response = await f.api.get(f.url("neighborhood"), params=params)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["truncated"]
    assert len(body["nodes"]) <= 100 and len(body["edges"]) <= 200
    assert len(body[cap]) == (100 if cap == "nodes" else 200)
    included = {node["id"] for node in body["nodes"]}
    assert all(
        {item["source_id"], item["target_id"]} <= included for item in body["edges"]
    )
    assert (await f.api.get(f.url("neighborhood"), params=params)).json() == body
    if cap == "nodes":
        # The center and its first 99 neighbors fill the first-hop node budget.
        # The existing edge from the first neighbor to f.nodes[2] stays out.
        assert body["depth"] == 2
        expected_targets = [f.nodes[1], *targets[:98]]
        assert [node["id"] for node in body["nodes"]] == [
            str(id_) for id_ in [f.nodes[0], *expected_targets]
        ]
        assert [item["target_id"] for item in body["edges"]] == [
            str(id_) for id_ in expected_targets
        ]
        assert all(item["source_id"] == str(f.nodes[0]) for item in body["edges"])
        depth_one = await f.api.get(
            f.url("neighborhood"), params={**params, "depth": 1}
        )
        assert depth_one.status_code == 200, depth_one.text
        assert depth_one.json() == {**body, "depth": 1}
