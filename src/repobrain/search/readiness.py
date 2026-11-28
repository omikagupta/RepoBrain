from uuid import UUID

from fastapi import APIRouter, Request

from repobrain.database.models import SearchIndex, VectorIndex
from repobrain.graph.exploration import Identity, load_snapshot
from repobrain.graph.routes import Db

router = APIRouter(prefix="/api/v1/snapshots", tags=["Search"])


class Readiness(Identity):
    graph_analyzed: bool
    lexical_version: str | None
    vector_version: str | None


@router.get(
    "/{snapshot_id}/readiness", summary="Read persisted analysis and index markers"
)
async def readiness(snapshot_id: UUID, session: Db, request: Request) -> Readiness:
    snapshot = await load_snapshot(session, snapshot_id)
    lexical = await session.get(SearchIndex, snapshot_id)
    vector = (
        await session.get(VectorIndex, snapshot_id)
        if request.app.state.tokens is None
        else None
    )
    return Readiness(
        **snapshot.identity.model_dump(),
        graph_analyzed=snapshot.counts is not None,
        lexical_version=lexical.chunking_version if lexical else None,
        vector_version=vector.vector_version if vector else None,
    )
