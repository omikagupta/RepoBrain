import asyncio
from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import ColumnElement, and_, case, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import defer

from repobrain.database.models import (
    ChunkEmbedding,
    IngestionState,
    RepositorySnapshot,
    SearchIndex,
    SourceChunk,
    SourceFile,
    VectorIndex,
)
from repobrain.graph.exploration import (
    ExplorationError,
    Identity,
    load_snapshot,
)
from repobrain.search.chunking import VERSION
from repobrain.search.embedding import (
    BATCH_SIZE,
    DIMENSION,
    MAX_INPUT_BYTES,
    EmbeddingModel,
    EmbeddingProvider,
    normalize,
)
from repobrain.search.service import Candidate, Match, make_match

VECTOR_VERSION = "cosine-exact-v1"
MAX_VECTOR_CHUNKS = 1000
BUILD_TIMEOUT = 600
PUBLISH_TIMEOUT = 45


class VectorSummary(BaseModel):
    snapshot_id: UUID
    chunking_version: str
    vector_version: str
    model: EmbeddingModel
    chunk_count: int
    reused: bool


class VectorResponse(Identity):
    query: str
    chunking_version: str
    vector_version: str
    model: EmbeddingModel
    metric: str = "cosine_similarity"
    results: list[Match]


@dataclass(frozen=True)
class ChunkInput:
    id: UUID
    digest: str
    content: str


def compatible(index: VectorIndex, model: EmbeddingModel) -> None:
    if (
        index.chunking_version != VERSION
        or index.vector_version != VECTOR_VERSION
        or index.model_id != model.model_id
        or index.model_revision != model.revision
        or index.dimension != model.dimension
        or index.encoding_policy != model.encoding_policy
    ):
        raise ExplorationError(
            409,
            "vector_index_incompatible",
            "Completed vector index uses a different version or model",
        )


def summary(
    index: VectorIndex, model: EmbeddingModel, *, reused: bool
) -> VectorSummary:
    compatible(index, model)
    return VectorSummary(
        snapshot_id=index.snapshot_id,
        chunking_version=index.chunking_version,
        vector_version=index.vector_version,
        model=model,
        chunk_count=index.chunk_count,
        reused=reused,
    )


async def lexical_index(session: AsyncSession, snapshot_id: UUID) -> SearchIndex:
    index = await session.get(SearchIndex, snapshot_id)
    if index is None or index.chunking_version != VERSION:
        raise ExplorationError(
            409, "search_index_unavailable", "Compatible lexical index is unavailable"
        )
    if index.chunk_count > MAX_VECTOR_CHUNKS:
        raise ExplorationError(
            422, "vector_chunk_limit", "Snapshot exceeds the vector chunk limit"
        )
    return index


def scoped_chunks(snapshot_id: UUID) -> tuple[ColumnElement[bool], ColumnElement[bool]]:
    return (
        SourceChunk.snapshot_id == snapshot_id,
        SourceChunk.chunking_version == VERSION,
    )


async def build_vector_index(
    sessions: async_sessionmaker[AsyncSession],
    snapshot_id: UUID,
    provider: EmbeddingProvider,
) -> VectorSummary:
    model = provider.model
    if model.dimension != DIMENSION:
        raise ExplorationError(
            503, "invalid_embedding", "Embedding dimension is incompatible"
        )
    try:
        async with asyncio.timeout(BUILD_TIMEOUT):
            async with sessions() as session:
                snapshot = await load_snapshot(session, snapshot_id)
                if snapshot.state != IngestionState.COMPLETED:
                    raise ExplorationError(
                        409, "snapshot_incomplete", "Snapshot ingestion is incomplete"
                    )
                existing = await session.get(VectorIndex, snapshot_id)
                if existing is not None:
                    return summary(existing, model, reused=True)
                source_index = await lexical_index(session, snapshot_id)
                rows = (
                    await session.execute(
                        select(
                            SourceChunk.id,
                            SourceChunk.content_sha256,
                            case(
                                (
                                    func.octet_length(SourceChunk.content)
                                    <= MAX_INPUT_BYTES,
                                    SourceChunk.content,
                                )
                            ),
                        )
                        .where(*scoped_chunks(snapshot_id))
                        .order_by(SourceChunk.stable_key)
                        .limit(MAX_VECTOR_CHUNKS + 1)
                    )
                ).all()
                if len(rows) != source_index.chunk_count:
                    raise ExplorationError(
                        409,
                        "source_chunks_changed",
                        "Stored chunk count does not match its index",
                    )
                inputs = []
                for id_, digest, content in rows:
                    if content is None:
                        raise ExplorationError(
                            422,
                            "vector_chunk_limit",
                            "Stored chunk exceeds the byte limit",
                        )
                    inputs.append(ChunkInput(id_, digest, content))
            vectors: list[list[float]] = []
            for offset in range(0, len(inputs), BATCH_SIZE):
                batch = [item.content for item in inputs[offset : offset + BATCH_SIZE]]
                vectors.extend(
                    normalize(
                        await provider.encode_documents(batch),
                        len(batch),
                        model.dimension,
                    )
                )
            return await publish(sessions, snapshot_id, model, inputs, vectors)
    except TimeoutError:
        raise ExplorationError(
            503, "vector_build_timeout", "Vector index build timed out"
        ) from None


async def publish(
    sessions: async_sessionmaker[AsyncSession],
    snapshot_id: UUID,
    model: EmbeddingModel,
    inputs: list[ChunkInput],
    vectors: list[list[float]],
) -> VectorSummary:
    async with asyncio.timeout(PUBLISH_TIMEOUT), sessions.begin() as session:
        await session.execute(
            text("SELECT set_config('statement_timeout', '45s', true)")
        )
        snapshot = await session.get(
            RepositorySnapshot, snapshot_id, with_for_update=True
        )
        if snapshot is None or snapshot.ingestion_state != IngestionState.COMPLETED:
            raise ExplorationError(
                409,
                "snapshot_incomplete",
                "Snapshot is no longer available for indexing",
            )
        existing = await session.get(VectorIndex, snapshot_id)
        if existing is not None:
            return summary(existing, model, reused=True)
        source_index = await lexical_index(session, snapshot_id)
        current = (
            await session.execute(
                select(SourceChunk.id, SourceChunk.content_sha256)
                .where(*scoped_chunks(snapshot_id))
                .order_by(SourceChunk.stable_key)
                .limit(MAX_VECTOR_CHUNKS + 1)
            )
        ).all()
        if source_index.chunk_count != len(inputs) or [
            (id_, digest) for id_, digest in current
        ] != [(item.id, item.digest) for item in inputs]:
            raise ExplorationError(
                409,
                "source_chunks_changed",
                "Stored chunks changed during vector indexing",
            )
        index = VectorIndex(
            snapshot_id=snapshot_id,
            chunking_version=VERSION,
            vector_version=VECTOR_VERSION,
            model_id=model.model_id,
            model_revision=model.revision,
            dimension=model.dimension,
            encoding_policy=model.encoding_policy,
            chunk_count=len(vectors),
        )
        session.add(index)
        await session.flush()
        session.add_all(
            ChunkEmbedding(
                chunk_id=item.id,
                snapshot_id=snapshot_id,
                chunking_version=VERSION,
                vector_version=VECTOR_VERSION,
                embedding=vector,
            )
            for item, vector in zip(inputs, vectors, strict=True)
        )
        return summary(index, model, reused=False)


async def vector_search(
    session: AsyncSession,
    snapshot_id: UUID,
    query: str,
    limit: int,
    provider: EmbeddingProvider,
) -> VectorResponse:
    if not query.strip() or "\x00" in query:
        raise ExplorationError(
            422, "invalid_search_query", "Vector search requires a nonempty query"
        )
    await session.execute(
        text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    )
    snapshot = await load_snapshot(session, snapshot_id)
    if snapshot.state != IngestionState.COMPLETED:
        raise ExplorationError(
            409, "snapshot_incomplete", "Snapshot ingestion is incomplete"
        )
    index = await session.get(VectorIndex, snapshot_id)
    if index is None:
        raise ExplorationError(
            409, "vector_index_unavailable", "Completed vector index is unavailable"
        )
    model = provider.model
    compatible(index, model)
    response = VectorResponse(
        **snapshot.identity.model_dump(),
        query=query,
        chunking_version=VERSION,
        vector_version=VECTOR_VERSION,
        model=model,
        results=[],
    )
    if not index.chunk_count:
        return response
    stamp = (index.completed_at, index.chunk_count)
    # Release the read transaction before potentially slow model initialization.
    await session.rollback()
    vector = normalize(await provider.encode_queries([query]), 1, DIMENSION)[0]
    # Validate and rank against one MVCC snapshot, including the source evidence.
    await session.execute(
        text("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ, READ ONLY")
    )
    current = await load_snapshot(session, snapshot_id)
    current_index = await session.get(VectorIndex, snapshot_id)
    if (
        current.identity != snapshot.identity
        or current.state != IngestionState.COMPLETED
        or current_index is None
        or (current_index.completed_at, current_index.chunk_count) != stamp
    ):
        raise ExplorationError(
            409, "vector_index_changed", "Vector index changed while encoding the query"
        )
    compatible(current_index, model)
    response.results = [
        candidate.match
        for candidate in await vector_candidates(
            session, current.identity, vector, limit
        )
    ]
    return response


async def vector_candidates(
    session: AsyncSession, identity: Identity, vector: list[float], limit: int
) -> list[Candidate]:
    distance = ChunkEmbedding.embedding.cosine_distance(vector).label("distance")
    rows = (
        await session.execute(
            select(SourceChunk, SourceFile.path, distance)
            .options(defer(SourceChunk.token_text), defer(SourceChunk.search_vector))
            .select_from(ChunkEmbedding)
            .join(
                SourceChunk,
                and_(
                    SourceChunk.id == ChunkEmbedding.chunk_id,
                    SourceChunk.snapshot_id == ChunkEmbedding.snapshot_id,
                    SourceChunk.chunking_version == ChunkEmbedding.chunking_version,
                ),
            )
            .join(
                SourceFile,
                and_(
                    SourceFile.id == SourceChunk.source_file_id,
                    SourceFile.snapshot_id == SourceChunk.snapshot_id,
                ),
            )
            .where(
                ChunkEmbedding.snapshot_id == identity.snapshot_id,
                ChunkEmbedding.chunking_version == VERSION,
                ChunkEmbedding.vector_version == VECTOR_VERSION,
            )
            .order_by(
                distance,
                SourceFile.path.collate("C"),
                SourceChunk.start_line,
                SourceChunk.stable_key,
            )
            .limit(limit)
        )
    ).all()
    return [
        Candidate(make_match(identity, chunk, path, 1 - value, rank), chunk.stable_key)
        for rank, (chunk, path, value) in enumerate(rows, 1)
    ]
