import asyncio
from hashlib import sha256
from uuid import UUID, uuid4

import pytest
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
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
from repobrain.graph import service
from repobrain.graph.analyzer import Analyzer, Edge, Graph, GraphError, InputFile
from repobrain.settings import Settings

FIXTURE = {
    "src/pkg/__init__.py": "",
    "src/pkg/tools.py": "def clean():\n    return 1\n",
    "src/pkg/main.py": (
        "import pkg.tools as tools\n"
        "from .tools import clean as wash\n"
        "from . import tools\n"
        "import unknown\n"
        "class Worker:\n"
        "    @(\n"
        "        decorated\n"
        "    )\n"
        "    async def handle(\n"
        "        self, obj,\n"
        "    ):\n"
        "        def run():\n"
        "            obj.clean()\n"
        "        return run\n"
        "def handle():\n"
        "    class Inner:\n"
        "        def run(self): pass\n"
        "    return getattr(Inner, 'run')\n"
    ),
    "rootpkg/__init__.py": "",
    "rootpkg/entry.py": "import rootpkg\n",
    "bad.py": "def broken(:\n",
}


def test_ast_graph_resolves_only_supported_relationships() -> None:
    files = [
        InputFile(id=uuid4(), path=path, content=code) for path, code in FIXTURE.items()
    ]
    snapshot = uuid4()
    graph = Analyzer(snapshot, files).build()
    assert graph == Analyzer(snapshot, list(reversed(files))).build()
    assert graph.analyzed_files == 5
    assert len(graph.nodes) == 13
    assert len(graph.edges) == 12
    nodes = {node.qualified_name: node for node in graph.nodes}
    method = nodes["pkg.main.Worker.handle"]
    assert (method.kind, method.is_async, method.start_line, method.end_line) == (
        "method",
        True,
        6,
        14,
    )
    assert (
        nodes["pkg.main.Worker.handle.run"].id != nodes["pkg.main.handle.Inner.run"].id
    )
    relationships = {
        (edge.source_id, edge.target_id, edge.relationship, edge.provenance)
        for edge in graph.edges
    }
    assert (
        nodes["pkg.main"].id,
        nodes["pkg.tools.clean"].id,
        "IMPORTS_SYMBOL",
        "from .tools import clean as wash",
    ) in relationships
    assert (
        nodes["pkg.main"].id,
        nodes["pkg.tools"].id,
        "IMPORTS",
        "pkg.tools as tools",
    ) in relationships
    assert {edge.relationship for edge in graph.edges} == {
        "CONTAINS",
        "IMPORTS",
        "IMPORTS_SYMBOL",
    }
    assert {item.code for item in graph.diagnostics} == {
        "syntax_error",
        "unresolved_import",
        "unresolved_symbol",
    }


def test_ambiguous_roots_and_rebound_symbols_are_not_inferred() -> None:
    files = [
        InputFile(id=uuid4(), path=path, content=code)
        for path, code in {
            "dupe.py": "",
            "src/dupe.py": "",
            "main.py": "import dupe\nfrom names import f\n",
            "names.py": "def f(): pass\ndef f(): pass\nf = object()\n",
        }.items()
    ]
    graph = Analyzer(uuid4(), files).build()
    assert len({node.id for node in graph.nodes}) == len(graph.nodes)
    assert {item.code for item in graph.diagnostics} == {
        "ambiguous_import",
        "unresolved_symbol",
    }
    assert [edge.relationship for edge in graph.edges].count("IMPORTS") == 1
    assert all(edge.relationship != "IMPORTS_SYMBOL" for edge in graph.edges)


async def seed(
    sessions: async_sessionmaker[AsyncSession],
    sha: str,
    state: IngestionState,
) -> UUID:
    async with sessions.begin() as session:
        repository = Repository(owner="sample", name=f"graph-{uuid4().hex}")
        session.add(repository)
        await session.flush()
        snapshot = RepositorySnapshot(
            repository_id=repository.id,
            commit_sha=sha,
            ingestion_state=state,
        )
        session.add(snapshot)
        await session.flush()
        session.add_all(
            SourceFile(
                snapshot_id=snapshot.id,
                path=path,
                content=content,
                content_sha256=sha256(content.encode()).hexdigest(),
                line_count=len(content.splitlines()),
                language="python",
            )
            for path, content in FIXTURE.items()
        )
        return snapshot.id


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_atomic_idempotent_graph_and_snapshot_constraints(
    migrated_database: Settings,
) -> None:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    try:
        first = await seed(sessions, "1" * 40, IngestionState.COMPLETED)
        second = await seed(sessions, "2" * 40, IngestionState.COMPLETED)
        a, b = await asyncio.gather(
            service.analyze_snapshot(sessions, first),
            service.analyze_snapshot(sessions, first),
        )
        assert sorted((a.reused, b.reused)) == [False, True]
        assert (a.commit_sha, a.analyzed_files, a.node_count, a.edge_count) == (
            "1" * 40,
            5,
            13,
            12,
        )
        await service.analyze_snapshot(sessions, second)
        async with sessions() as session:
            nodes = select(GraphNode.id).order_by(GraphNode.stable_key).limit(1)
            source = await session.scalar(nodes.where(GraphNode.snapshot_id == first))
            foreign = await session.scalar(nodes.where(GraphNode.snapshot_id == second))
            assert source is not None and foreign is not None and source != foreign
            counts = await session.get(GraphAnalysis, first)
            assert counts is not None and len(counts.diagnostics) == 3
        with pytest.raises(IntegrityError):
            async with sessions.begin() as session:
                session.add(
                    GraphEdge(
                        id=uuid4(),
                        snapshot_id=first,
                        source_id=source,
                        target_id=foreign,
                        stable_key="0" * 64,
                        relationship="IMPORTS",
                        provenance="invalid",
                    )
                )
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_failed_write_rolls_back_entire_graph(
    migrated_database: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    parse = service.parse_files

    async def corrupt(snapshot_id: UUID, files: list[InputFile]) -> Graph:
        graph = await parse(snapshot_id, files)
        edge = graph.edges[0]
        assert isinstance(edge, Edge)
        edge.target_id = uuid4()
        return graph

    try:
        pending = await seed(sessions, "3" * 40, IngestionState.PENDING)
        with pytest.raises(GraphError, match="completed ingestion"):
            await service.analyze_snapshot(sessions, pending)
        completed = await seed(sessions, "4" * 40, IngestionState.COMPLETED)
        with monkeypatch.context() as patch:
            patch.setattr(service, "parse_files", corrupt)
            with pytest.raises(IntegrityError):
                await service.analyze_snapshot(sessions, completed)
        async with sessions() as session:
            assert await session.get(GraphAnalysis, completed) is None
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(GraphNode)
                    .where(GraphNode.snapshot_id == completed)
                )
                == 0
            )
        assert (await service.analyze_snapshot(sessions, completed)).node_count == 13
    finally:
        await engine.dispose()
