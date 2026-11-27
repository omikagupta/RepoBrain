from collections.abc import AsyncIterator
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repobrain.graph.exploration import (
    MAX_STORED_BYTES,
    Direction,
    EdgeFilters,
    EdgeView,
    ExplorationError,
    Neighborhood,
    NodeFilters,
    NodeView,
    Page,
    Relationship,
    SourceView,
    Summary,
    list_edges,
    list_nodes,
    load_snapshot,
    neighborhood,
    read_source,
    require_graph,
)
from repobrain.ingestion.routes import ErrorEnvelope

router = APIRouter(
    prefix="/api/v1/snapshots/{snapshot_id}",
    tags=["Graph exploration"],
    responses={code: {"model": ErrorEnvelope} for code in (404, 409, 422, 500, 503)},
)


async def read_session(request: Request) -> AsyncIterator[AsyncSession]:
    sessions: async_sessionmaker[AsyncSession] | None = getattr(
        request.app.state, "database_sessions", None
    )
    if sessions is None:
        raise ExplorationError(503, "database_unavailable", "Database is unavailable")
    async with sessions() as session:
        yield session


Db = Annotated[AsyncSession, Depends(read_session)]


@router.get("/graph", summary="Get graph counts for an analyzed snapshot")
async def graph_summary(snapshot_id: UUID, session: Db) -> Summary:
    snapshot = await load_snapshot(session, snapshot_id)
    files, nodes, edges, diagnostics = require_graph(snapshot)
    return Summary(
        **snapshot.identity.model_dump(),
        analyzed_files=files,
        node_count=nodes,
        edge_count=edges,
        diagnostic_count=diagnostics,
    )


@router.get("/nodes", summary="List nodes in stable key order")
async def nodes(
    snapshot_id: UUID, session: Db, filters: Annotated[NodeFilters, Query()]
) -> Page[NodeView]:
    require_graph(await load_snapshot(session, snapshot_id))
    return await list_nodes(session, snapshot_id, filters)


@router.get("/edges", summary="List directed edges in stable key order")
async def edges(
    snapshot_id: UUID, session: Db, filters: Annotated[EdgeFilters, Query()]
) -> Page[EdgeView]:
    require_graph(await load_snapshot(session, snapshot_id))
    return await list_edges(session, snapshot_id, filters)


@router.get(
    "/neighborhood", summary="Read a bounded, optionally truncated neighborhood"
)
async def graph_neighborhood(
    snapshot_id: UUID,
    session: Db,
    node_id: Annotated[UUID, Query(description="Center node UUID")],
    direction: Annotated[
        Direction, Query(description="Edge direction from each frontier")
    ] = "both",
    depth: Annotated[int, Query(ge=1, le=2)] = 1,
    relationship: Annotated[list[Relationship] | None, Query(max_length=3)] = None,
) -> Neighborhood:
    require_graph(await load_snapshot(session, snapshot_id))
    return await neighborhood(
        session, snapshot_id, node_id, direction, 1 if depth == 1 else 2, relationship
    )


@router.get(
    "/source", summary="Read an inclusive source window from a completed snapshot"
)
async def source(
    snapshot_id: UUID,
    session: Db,
    path: Annotated[
        str, Query(min_length=1, max_length=1024, description="Exact POSIX path")
    ],
    start_line: Annotated[int | None, Query(ge=1, le=MAX_STORED_BYTES)] = None,
    end_line: Annotated[int | None, Query(ge=1, le=MAX_STORED_BYTES)] = None,
) -> SourceView:
    snapshot = await load_snapshot(session, snapshot_id)
    return await read_source(session, snapshot, path, start_line, end_line)
