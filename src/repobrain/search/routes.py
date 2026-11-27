from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query

from repobrain.graph.routes import Db
from repobrain.ingestion.routes import ErrorEnvelope
from repobrain.search.service import SearchResponse, lexical_search

router = APIRouter(
    prefix="/api/v1/snapshots/{snapshot_id}/search",
    tags=["Search"],
    responses={code: {"model": ErrorEnvelope} for code in (404, 409, 422, 500, 503)},
)


@router.get("/lexical", summary="Rank stored Python chunks by lexical relevance")
async def search(
    snapshot_id: UUID,
    session: Db,
    q: Annotated[str, Query(min_length=1, max_length=256)],
    limit: Annotated[int, Query(ge=1, le=30)] = 10,
) -> SearchResponse:
    return await lexical_search(session, snapshot_id, q, limit)
