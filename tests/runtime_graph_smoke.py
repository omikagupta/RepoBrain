"""Run from the non-root runtime image against the isolated Compose database."""

import asyncio
import json
import os
import subprocess
import sys
from hashlib import sha256
from uuid import UUID

from sqlalchemy import inspect, select, text
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
from repobrain.graph.service import GraphSummary
from repobrain.settings import Settings


def run_module(*args: str) -> bytes:
    return subprocess.run(
        [sys.executable, "-I", "-m", *args], check=True, capture_output=True, timeout=60
    ).stdout


async def seed(sessions: async_sessionmaker[AsyncSession]) -> UUID:
    async with sessions.begin() as session:
        repository = Repository(owner="sample", name="runtime-smoke")
        session.add(repository)
        await session.flush()
        snapshot = RepositorySnapshot(
            repository_id=repository.id,
            commit_sha="a" * 40,
            ingestion_state=IngestionState.COMPLETED,
        )
        session.add(snapshot)
        await session.flush()
        for path, source in {
            "app.py": "from util import collect\n",
            "util.py": "def collect():\n    return 1\n",
        }.items():
            session.add(
                SourceFile(
                    snapshot_id=snapshot.id,
                    path=path,
                    content=source,
                    language="python",
                    content_sha256=sha256(source.encode()).hexdigest(),
                    line_count=len(source.splitlines()),
                )
            )
        return snapshot.id


async def smoke() -> None:
    assert os.geteuid() == 10001
    engine = create_database_engine(Settings())
    sessions = create_session_factory(engine)
    try:
        async with engine.connect() as connection:
            database = await connection.scalar(text("SELECT current_database()"))
            tables = await connection.run_sync(
                lambda conn: inspect(conn).get_table_names()
            )
            if database != "repobrain_test" or tables:
                raise RuntimeError(
                    "Runtime smoke test requires the fresh disposable test database"
                )
        await asyncio.to_thread(run_module, "alembic", "upgrade", "head")
        await asyncio.to_thread(run_module, "alembic", "check")
        snapshot = await seed(sessions)
        raw = await asyncio.to_thread(run_module, "repobrain.graph", str(snapshot))
        summary = GraphSummary.model_validate_json(raw)
        assert (summary.analyzed_files, summary.node_count, summary.edge_count) == (
            2,
            3,
            3,
        )
        assert summary.commit_sha == "a" * 40
        async with sessions() as session:
            analysis = await session.get(GraphAnalysis, snapshot)
            assert analysis is not None and not analysis.diagnostics
            nodes = await session.scalars(
                select(GraphNode.qualified_name).where(
                    GraphNode.snapshot_id == snapshot
                )
            )
            edges = await session.scalars(
                select(GraphEdge.relationship).where(GraphEdge.snapshot_id == snapshot)
            )
            assert sorted(nodes.all()) == ["app", "util", "util.collect"]
            assert sorted(edges.all()) == ["CONTAINS", "IMPORTS", "IMPORTS_SYMBOL"]
        print(json.dumps({"uid": os.geteuid(), **summary.model_dump(mode="json")}))
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(smoke())
