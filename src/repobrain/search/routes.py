from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Query, Request

from repobrain.graph.routes import Db
from repobrain.ingestion.routes import ErrorEnvelope
from repobrain.search.embedding import EmbeddingProvider, unavailable
from repobrain.search.graph_enhanced import (
    MAX_RESULTS,
    GraphSearchResponse,
    graph_search,
)
from repobrain.search.hybrid import HybridResponse, hybrid_search
from repobrain.search.service import SearchResponse, lexical_search
from repobrain.search.vector import VectorResponse, vector_search

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


@router.get("/vector", summary="Rank persisted chunks by exact cosine similarity")
async def semantic_search(
    snapshot_id: UUID,
    session: Db,
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=512)],
    limit: Annotated[int, Query(ge=1, le=30)] = 10,
) -> VectorResponse:
    return await vector_search(session, snapshot_id, q, limit, get_provider(request))


@router.get("/hybrid", summary="Fuse lexical and vector ranks for stored Python chunks")
async def fused_search(
    snapshot_id: UUID,
    session: Db,
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=256)],
    limit: Annotated[int, Query(ge=1, le=30)] = 10,
) -> HybridResponse:
    return await hybrid_search(session, snapshot_id, q, limit, get_provider(request))


@router.get("/graph-enhanced", summary="Expand hybrid hits through the stored graph")
async def graph_enhanced_search(
    snapshot_id: UUID,
    session: Db,
    request: Request,
    q: Annotated[str, Query(min_length=1, max_length=256)],
    limit: Annotated[int, Query(ge=1, le=MAX_RESULTS)] = 10,
) -> GraphSearchResponse:
    return await graph_search(session, snapshot_id, q, limit, get_provider(request))


def get_provider(request: Request) -> EmbeddingProvider:
    provider: EmbeddingProvider | None = getattr(
        request.app.state, "embedding_provider", None
    )
    if provider is None:
        raise unavailable("Embedding provider is unavailable")
    return provider
