from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from datetime import datetime
from fractions import Fraction
from typing import Final, Literal
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from repobrain.database.models import IngestionState, VectorIndex
from repobrain.graph.exploration import ExplorationError, Identity, load_snapshot
from repobrain.search.chunking import VERSION
from repobrain.search.embedding import (
    DIMENSION,
    EmbeddingModel,
    EmbeddingProvider,
    normalize,
    unavailable,
)
from repobrain.search.service import (
    Candidate,
    Match,
    lexical_candidates,
    lexical_index,
    query_terms,
)
from repobrain.search.vector import VECTOR_VERSION, compatible, vector_candidates

POOL_SIZE: Final = 30
RRF_K: Final = 60


class FusionPolicy(BaseModel):
    version: Literal["rrf-v1"] = "rrf-v1"
    k: Literal[60] = RRF_K
    lexical_candidate_limit: Literal[30] = POOL_SIZE
    vector_candidate_limit: Literal[30] = POOL_SIZE
    lexical_weight: Literal[1] = 1
    vector_weight: Literal[1] = 1
    renormalize_missing_channels: Literal[False] = False


class HybridMatch(Match):
    lexical_rank: int | None
    lexical_score: float | None
    vector_rank: int | None
    vector_score: float | None
    channels: list[Literal["lexical", "vector"]]


class RetrievalIdentity(Identity):
    query: str
    chunking_version: str
    vector_version: str
    model: EmbeddingModel
    fusion: FusionPolicy


class HybridResponse(RetrievalIdentity):
    results: list[HybridMatch]


def rrf_score(lexical_rank: int | None, vector_rank: int | None) -> Fraction:
    return sum(
        (
            Fraction(1, RRF_K + rank)
            for rank in (lexical_rank, vector_rank)
            if rank is not None
        ),
        Fraction(),
    )


def fuse(
    lexical: Sequence[Candidate], vector: Sequence[Candidate], limit: int
) -> list[HybridMatch]:
    # Candidate lists are already ranked. Keep the first occurrence per channel.
    lexical_by_id: dict[UUID, Candidate] = {}
    vector_by_id: dict[UUID, Candidate] = {}
    for hit in lexical:
        lexical_by_id.setdefault(hit.match.chunk_id, hit)
    for hit in vector:
        vector_by_id.setdefault(hit.match.chunk_id, hit)

    ranked: list[tuple[Fraction, str, int, str, HybridMatch]] = []
    for chunk_id, hit in (vector_by_id | lexical_by_id).items():
        lex = lexical_by_id.get(chunk_id)
        vec = vector_by_id.get(chunk_id)
        lexical_rank = lex.match.rank if lex else None
        vector_rank = vec.match.rank if vec else None
        score = rrf_score(lexical_rank, vector_rank)
        channels: list[Literal["lexical", "vector"]] = []
        if lex is not None:
            channels.append("lexical")
        if vec is not None:
            channels.append("vector")
        match = HybridMatch(
            **hit.match.model_dump(exclude={"score"}),
            score=float(score),
            lexical_rank=lexical_rank,
            lexical_score=lex.match.score if lex else None,
            vector_rank=vector_rank,
            vector_score=vec.match.score if vec else None,
            channels=channels,
        )
        ranked.append((-score, match.path, match.start_line, hit.stable_key, match))

    ranked.sort(key=lambda entry: entry[:4])
    return [
        match.model_copy(update={"rank": rank})
        for rank, (*_, match) in enumerate(ranked[:limit], 1)
    ]


@dataclass(frozen=True)
class Indexes:
    identity: Identity
    chunk_count: int
    lexical_built_at: datetime
    vector_completed_at: datetime


async def read_indexes(
    session: AsyncSession, snapshot_id: UUID, model: EmbeddingModel
) -> Indexes:
    await session.execute(
        text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    )
    snapshot = await load_snapshot(session, snapshot_id)
    if snapshot.state != IngestionState.COMPLETED:
        raise ExplorationError(
            409, "snapshot_incomplete", "Snapshot ingestion is incomplete"
        )
    lexical = await lexical_index(session, snapshot_id)
    vector = await session.get(VectorIndex, snapshot_id)
    if vector is None:
        raise ExplorationError(
            409, "vector_index_unavailable", "Completed vector index is unavailable"
        )
    compatible(vector, model)
    if lexical.chunk_count != vector.chunk_count:
        raise ExplorationError(
            409, "hybrid_indexes_incompatible", "Lexical and vector indexes disagree"
        )
    return Indexes(
        snapshot.identity, lexical.chunk_count, lexical.built_at, vector.completed_at
    )


async def hybrid_search(
    session: AsyncSession,
    snapshot_id: UUID,
    query: str,
    limit: int,
    provider: EmbeddingProvider,
    *,
    prerequisite: Callable[[], Awaitable[str]] | None = None,
) -> HybridResponse:
    if "\x00" in query:
        raise ExplorationError(
            422, "invalid_search_query", "Search contains a NUL byte"
        )
    terms = query_terms(query)
    model = provider.model
    indexes = await read_indexes(session, snapshot_id, model)
    prerequisite_stamp = await prerequisite() if prerequisite is not None else None
    lexical: list[Candidate] = []
    vector: list[Candidate] = []
    if indexes.chunk_count:
        # Do not retain a database transaction during native inference.
        await session.rollback()
        embedding = normalize(await provider.encode_queries([query]), 1, DIMENSION)[0]
        if provider.model != model:
            raise unavailable("Embedding provider changed while encoding the query")
        # Recheck readiness and rank both channels in this single MVCC snapshot.
        current = await read_indexes(session, snapshot_id, model)
        if current != indexes:
            raise ExplorationError(
                409, "hybrid_indexes_changed", "Search indexes changed during inference"
            )
        if prerequisite is not None and await prerequisite() != prerequisite_stamp:
            raise ExplorationError(
                409, "graph_analysis_changed", "Graph analysis changed during inference"
            )
        lexical = await lexical_candidates(session, current.identity, terms, POOL_SIZE)
        vector = await vector_candidates(
            session, current.identity, embedding, POOL_SIZE
        )
    return HybridResponse(
        **indexes.identity.model_dump(),
        query=query,
        chunking_version=VERSION,
        vector_version=VECTOR_VERSION,
        model=model,
        fusion=FusionPolicy(),
        results=fuse(lexical, vector, limit),
    )
