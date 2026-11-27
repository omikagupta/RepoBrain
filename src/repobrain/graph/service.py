import asyncio
import sys
from uuid import UUID

from pydantic import BaseModel, ValidationError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repobrain.database.models import (
    GraphAnalysis,
    GraphEdge,
    GraphNode,
    IngestionState,
    RepositorySnapshot,
    SourceFile,
)
from repobrain.graph.analyzer import (
    MAX_FILE_BYTES,
    MAX_FILES,
    MAX_TOTAL_BYTES,
    Graph,
    GraphError,
    InputFile,
)
from repobrain.graph.worker import files_adapter

TIMEOUT = 45


class GraphSummary(BaseModel):
    snapshot_id: UUID
    commit_sha: str
    analyzed_files: int
    node_count: int
    edge_count: int
    diagnostic_count: int
    reused: bool


async def read_files(session: AsyncSession, snapshot_id: UUID) -> list[InputFile]:
    byte_size = func.octet_length(SourceFile.content)
    metadata = (
        await session.execute(
            select(SourceFile.id, byte_size)
            .where(
                SourceFile.snapshot_id == snapshot_id, SourceFile.language == "python"
            )
            .order_by(SourceFile.path)
            .limit(MAX_FILES + 1)
        )
    ).all()
    if (
        len(metadata) > MAX_FILES
        or any(size > MAX_FILE_BYTES for _, size in metadata)
        or sum(size for _, size in metadata) > MAX_TOTAL_BYTES
    ):
        raise GraphError("Snapshot exceeds graph input limits")
    if not metadata:
        return []
    by_id: dict[UUID, int] = {id_: size for id_, size in metadata}
    result = await session.stream(
        select(SourceFile.id, SourceFile.path, SourceFile.content, byte_size)
        .where(
            SourceFile.snapshot_id == snapshot_id,
            SourceFile.id.in_(by_id),
            byte_size <= MAX_FILE_BYTES,
        )
        .order_by(SourceFile.path)
        .execution_options(yield_per=20)
    )
    try:
        files = []
        async for id_, path, content, size in result:
            if size != by_id[id_]:
                raise GraphError("Snapshot changed while reading source files")
            files.append(InputFile(id=id_, path=path, content=content))
        if len(files) != len(metadata):
            raise GraphError("Snapshot changed while reading source files")
        return files
    finally:
        await result.close()


async def parse_files(snapshot_id: UUID, files: list[InputFile]) -> Graph:
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-I",
        "-m",
        "repobrain.graph.worker",
        str(snapshot_id),
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.DEVNULL,
    )
    try:
        output, _ = await process.communicate(files_adapter.dump_json(files))
    finally:
        if process.returncode is None:
            try:
                process.kill()
            except ProcessLookupError:
                pass
            await process.communicate()
    if process.returncode == 2:
        raise GraphError(output.decode("ascii"))
    if process.returncode:
        raise GraphError("Python parser process failed")
    try:
        return Graph.model_validate_json(output)
    except ValidationError:
        raise GraphError("Python parser produced an invalid graph") from None


async def analyze_snapshot(
    sessions: async_sessionmaker[AsyncSession], snapshot_id: UUID
) -> GraphSummary:
    async with asyncio.timeout(TIMEOUT), sessions.begin() as session:
        await session.execute(
            text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": f"{TIMEOUT}s"},
        )
        snapshot = await session.get(
            RepositorySnapshot, snapshot_id, with_for_update=True
        )
        if snapshot is None or snapshot.ingestion_state != IngestionState.COMPLETED:
            raise GraphError("Snapshot must exist and have completed ingestion")

        analysis = await session.get(GraphAnalysis, snapshot_id)
        reused = analysis is not None
        if analysis is None:
            graph = await parse_files(
                snapshot_id, await read_files(session, snapshot_id)
            )
            analysis = GraphAnalysis(
                snapshot_id=snapshot_id,
                analyzed_files=graph.analyzed_files,
                node_count=len(graph.nodes),
                edge_count=len(graph.edges),
                diagnostics=[item.model_dump() for item in graph.diagnostics],
            )
            session.add(analysis)
            await session.flush()
            session.add_all(
                GraphNode(snapshot_id=snapshot_id, **node.model_dump())
                for node in graph.nodes
            )
            await session.flush()
            session.add_all(
                GraphEdge(snapshot_id=snapshot_id, **edge.model_dump())
                for edge in graph.edges
            )
        return GraphSummary(
            snapshot_id=snapshot_id,
            commit_sha=snapshot.commit_sha,
            analyzed_files=analysis.analyzed_files,
            node_count=analysis.node_count,
            edge_count=analysis.edge_count,
            diagnostic_count=len(analysis.diagnostics),
            reused=reused,
        )
