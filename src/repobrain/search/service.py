import asyncio
from collections import defaultdict
from dataclasses import dataclass
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import and_, func, literal_column, select, text
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from sqlalchemy.orm import defer

from repobrain.database.models import (
    IngestionState,
    RepositorySnapshot,
    SearchIndex,
    SourceChunk,
    SourceFile,
)
from repobrain.graph.analyzer import GraphError, Node
from repobrain.graph.exploration import (
    ExplorationError,
    Identity,
    checked_path,
    load_snapshot,
    source_permalink,
)
from repobrain.graph.service import parse_files, read_files
from repobrain.search.chunking import (
    MAX_CHUNKS,
    VERSION,
    chunk_file,
    lexeme,
    search_terms,
)

BUILD_TIMEOUT = 60
MAX_QUERY_TERMS = 32


class BuildSummary(BaseModel):
    snapshot_id: UUID
    commit_sha: str
    chunking_version: str
    chunk_count: int
    indexed_files: int
    indexed_bytes: int
    reused: bool


class Match(Identity):
    chunk_id: UUID
    source_file_id: UUID
    path: str
    start_line: int
    end_line: int
    text: str
    source_sha256: str
    content_sha256: str
    score: float
    rank: int
    permalink: str


class SearchResponse(Identity):
    query: str
    chunking_version: str
    results: list[Match]


async def build_index(
    sessions: async_sessionmaker[AsyncSession], snapshot_id: UUID
) -> BuildSummary:
    async with asyncio.timeout(BUILD_TIMEOUT), sessions.begin() as session:
        await session.execute(
            text("SELECT set_config('statement_timeout', :timeout, true)"),
            {"timeout": f"{BUILD_TIMEOUT}s"},
        )
        snapshot = await session.get(
            RepositorySnapshot, snapshot_id, with_for_update=True
        )
        if snapshot is None or snapshot.ingestion_state != IngestionState.COMPLETED:
            raise GraphError("Snapshot must exist and have completed ingestion")
        index = await session.get(SearchIndex, snapshot_id)
        reused = index is not None
        if index is not None and index.chunking_version != VERSION:
            raise GraphError(
                "Snapshot already has an index from a different chunking version"
            )
        if index is None:
            files = await read_files(session, snapshot_id)
            graph = await parse_files(snapshot_id, files)
            symbols: dict[UUID, list[Node]] = defaultdict(list)
            for node in graph.nodes:
                symbols[node.source_file_id].append(node)
            chunks: list[SourceChunk] = []
            for source in files:
                for chunk in chunk_file(snapshot_id, source, symbols[source.id]):
                    if len(chunks) >= MAX_CHUNKS:
                        raise GraphError("Lexical chunk count limit exceeded")
                    chunks.append(chunk)
            index = SearchIndex(
                snapshot_id=snapshot_id,
                chunking_version=VERSION,
                chunk_count=len(chunks),
                indexed_files=len({chunk.source_file_id for chunk in chunks}),
                indexed_bytes=sum(len(chunk.content.encode()) for chunk in chunks),
            )
            session.add(index)
            await session.flush()
            session.add_all(chunks)
        return BuildSummary(
            snapshot_id=snapshot_id,
            commit_sha=snapshot.commit_sha,
            chunking_version=VERSION,
            chunk_count=index.chunk_count,
            indexed_files=index.indexed_files,
            indexed_bytes=index.indexed_bytes,
            reused=reused,
        )


@dataclass(frozen=True)
class Candidate:
    match: Match
    stable_key: str


def make_match(
    identity: Identity, chunk: SourceChunk, path: str, value: float, rank: int
) -> Match:
    return Match(
        **identity.model_dump(),
        chunk_id=chunk.id,
        source_file_id=chunk.source_file_id,
        path=path,
        start_line=chunk.start_line,
        end_line=chunk.end_line,
        text=chunk.content,
        source_sha256=chunk.source_sha256,
        content_sha256=chunk.content_sha256,
        score=value,
        rank=rank,
        permalink=source_permalink(
            identity, checked_path(path), chunk.start_line, chunk.end_line
        ),
    )


def query_terms(query: str) -> list[str]:
    terms = list(dict.fromkeys(search_terms(query)))
    if not terms or len(terms) > MAX_QUERY_TERMS:
        raise ExplorationError(
            422, "invalid_search_query", "Search requires 1 to 32 distinct terms"
        )
    return terms


async def lexical_index(session: AsyncSession, snapshot_id: UUID) -> SearchIndex:
    index = await session.get(SearchIndex, snapshot_id)
    if index is None or index.chunking_version != VERSION:
        raise ExplorationError(
            409, "search_index_unavailable", "Compatible lexical index is unavailable"
        )
    return index


async def lexical_search(
    session: AsyncSession, snapshot_id: UUID, query: str, limit: int
) -> SearchResponse:
    terms = query_terms(query)
    snapshot = await load_snapshot(session, snapshot_id)
    if snapshot.state != IngestionState.COMPLETED:
        raise ExplorationError(
            409, "snapshot_incomplete", "Snapshot ingestion is incomplete"
        )
    index = await lexical_index(session, snapshot_id)
    candidates = await lexical_candidates(session, snapshot.identity, terms, limit)
    return SearchResponse(
        **snapshot.identity.model_dump(),
        query=query,
        chunking_version=index.chunking_version,
        results=[candidate.match for candidate in candidates],
    )


async def lexical_candidates(
    session: AsyncSession, identity: Identity, terms: list[str], limit: int
) -> list[Candidate]:
    tsquery = func.plainto_tsquery(
        literal_column("'simple'::regconfig"), " ".join(map(lexeme, terms))
    )
    score = func.ts_rank(SourceChunk.search_vector, tsquery, 32).label("score")
    rows = (
        await session.execute(
            select(SourceChunk, SourceFile.path, score)
            .options(defer(SourceChunk.token_text), defer(SourceChunk.search_vector))
            .join(
                SourceFile,
                and_(
                    SourceFile.id == SourceChunk.source_file_id,
                    SourceFile.snapshot_id == SourceChunk.snapshot_id,
                ),
            )
            .where(
                SourceChunk.snapshot_id == identity.snapshot_id,
                SourceChunk.chunking_version == VERSION,
                SourceChunk.search_vector.bool_op("@@")(tsquery),
            )
            .order_by(
                score.desc(),
                SourceFile.path.collate("C"),
                SourceChunk.start_line,
                SourceChunk.stable_key,
            )
            .limit(limit)
        )
    ).all()
    return [
        Candidate(make_match(identity, chunk, path, value, rank), chunk.stable_key)
        for rank, (chunk, path, value) in enumerate(rows, 1)
    ]
