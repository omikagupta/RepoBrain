from dataclasses import dataclass
from fractions import Fraction
from typing import Literal, cast
from uuid import UUID

from pydantic import BaseModel
from sqlalchemy import String, and_, case, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from repobrain.database.models import (
    GraphAnalysis,
    GraphEdge,
    GraphNode,
    SourceChunk,
    SourceFile,
)
from repobrain.graph.exploration import (
    RELATIONSHIPS,
    ExplorationError,
    Identity,
    Relationship,
)
from repobrain.search.chunking import VERSION
from repobrain.search.embedding import EmbeddingProvider
from repobrain.search.hybrid import (
    POOL_SIZE,
    HybridMatch,
    RetrievalIdentity,
    hybrid_search,
    rrf_score,
)
from repobrain.search.service import Match, make_match

MAX_SEEDS = 5
MAX_DEPTH = 2
MAX_NODES = 50
MAX_EDGES = 100
MAX_EXPANDED = 30
MAX_RESULTS = 30
GRAPH_WEIGHT = Fraction(3, 4)


class ExpansionPolicy(BaseModel):
    version: str = "graph-outgoing-v1"
    ranking_version: str = "rrf-plus-best-hop-v1"
    direction: Literal["outgoing"] = "outgoing"
    relationships: tuple[Relationship, ...] = RELATIONSHIPS
    seed_limit: int = MAX_SEEDS
    depth_limit: int = MAX_DEPTH
    node_limit: int = MAX_NODES
    edge_limit: int = MAX_EDGES
    expanded_chunk_limit: int = MAX_EXPANDED
    result_limit: int = MAX_RESULTS
    graph_weight: float = float(GRAPH_WEIGHT)


class TraversalStats(BaseModel):
    seed_count: int
    mapped_seed_count: int
    visited_nodes: int
    traversed_edges: int
    expanded_chunks: int
    depth_reached: int
    depth_limit_reached: bool
    node_limit_reached: bool
    edge_limit_reached: bool
    chunk_limit_reached: bool
    truncated: bool


class PathEdge(BaseModel):
    edge_id: UUID
    source_node_id: UUID
    target_node_id: UUID
    relationship: Relationship


class Provenance(BaseModel):
    seed_chunk_id: UUID
    seed_rank: int
    seed_score: float
    node_ids: tuple[UUID, ...]
    edges: tuple[PathEdge, ...]
    hop_count: int


class GraphMatch(Match):
    hybrid_rank: int | None
    hybrid_score: float | None
    graph_contribution: float
    channels: list[Literal["lexical", "vector", "graph"]]
    provenance: Provenance | None


class GraphSearchResponse(RetrievalIdentity):
    expansion: ExpansionPolicy
    traversal: TraversalStats
    results: list[GraphMatch]


@dataclass(frozen=True)
class Walk:
    seed: HybridMatch
    nodes: tuple[UUID, ...]
    edges: tuple[PathEdge, ...] = ()

    @property
    def contribution(self) -> Fraction:
        return (
            GRAPH_WEIGHT
            * rrf_score(self.seed.lexical_rank, self.seed.vector_rank)
            / len(self.edges)
        )

    def evidence(self) -> Provenance:
        return Provenance(
            seed_chunk_id=self.seed.chunk_id,
            seed_rank=self.seed.rank,
            seed_score=self.seed.score,
            node_ids=self.nodes,
            edges=self.edges,
            hop_count=len(self.edges),
        )


async def analysis_stamp(session: AsyncSession, snapshot_id: UUID) -> str:
    # The atomic analysis marker has no version column. xmin detects a replacement
    # or update during inference, even when the stored counts stay the same.
    stamp = await session.scalar(
        select(literal_column("graph_analyses.xmin::text", type_=String()))
        .select_from(GraphAnalysis)
        .where(GraphAnalysis.snapshot_id == snapshot_id)
    )
    if stamp is None:
        raise ExplorationError(
            409, "graph_analysis_unavailable", "Completed graph analysis is unavailable"
        )
    return stamp


async def seed_nodes(
    session: AsyncSession, snapshot_id: UUID, seeds: list[HybridMatch]
) -> dict[UUID, UUID]:
    if not seeds:
        return {}
    overlap = (
        func.least(GraphNode.end_line, SourceChunk.end_line)
        - func.greatest(GraphNode.start_line, SourceChunk.start_line)
        + 1
    )
    priority = func.row_number().over(
        partition_by=SourceChunk.id,
        order_by=(
            case((GraphNode.kind == "module", 1), else_=0),
            overlap.desc(),
            (GraphNode.end_line - GraphNode.start_line).asc().nulls_last(),
            GraphNode.stable_key,
        ),
    )
    choices = (
        select(
            SourceChunk.id.label("chunk_id"),
            GraphNode.id.label("node_id"),
            priority.label("priority"),
        )
        .join(
            GraphNode,
            and_(
                GraphNode.snapshot_id == SourceChunk.snapshot_id,
                GraphNode.source_file_id == SourceChunk.source_file_id,
            ),
        )
        .where(
            SourceChunk.snapshot_id == snapshot_id,
            SourceChunk.chunking_version == VERSION,
            SourceChunk.id.in_([seed.chunk_id for seed in seeds]),
            (GraphNode.kind == "module")
            | and_(
                GraphNode.start_line <= SourceChunk.end_line,
                GraphNode.end_line >= SourceChunk.start_line,
            ),
        )
        .subquery()
    )
    rows = await session.execute(
        select(choices.c.chunk_id, choices.c.node_id).where(choices.c.priority == 1)
    )
    return {chunk: node for chunk, node in rows}


async def walk_graph(
    session: AsyncSession, snapshot_id: UUID, starts: dict[UUID, Walk]
) -> tuple[dict[UUID, Walk], int, bool, bool, bool]:
    visited = set(starts)
    frontier = starts
    discovered: dict[UUID, Walk] = {}
    edges = 0
    node_cap = edge_cap = False
    for _ in range(MAX_DEPTH):
        if not frontier:
            break
        rows = await session.scalars(
            select(GraphEdge)
            .where(
                GraphEdge.snapshot_id == snapshot_id,
                GraphEdge.source_id.in_(frontier),
                GraphEdge.relationship.in_(RELATIONSHIPS),
            )
            .order_by(GraphEdge.stable_key)
            .limit(MAX_EDGES - edges + 1)
        )
        next_level: dict[UUID, Walk] = {}
        for edge in rows:
            if edges == MAX_EDGES:
                edge_cap = True
                break
            edges += 1
            if edge.target_id in visited:
                continue
            if len(visited) == MAX_NODES:
                node_cap = True
                break
            path = frontier[edge.source_id]
            step = PathEdge(
                edge_id=edge.id,
                source_node_id=edge.source_id,
                target_node_id=edge.target_id,
                relationship=cast(Relationship, edge.relationship),
            )
            next_level[edge.target_id] = Walk(
                path.seed, (*path.nodes, edge.target_id), (*path.edges, step)
            )
            visited.add(edge.target_id)
        discovered.update(next_level)
        if node_cap or edge_cap:
            break
        frontier = next_level
    depth_cap = False
    if frontier and not (node_cap or edge_cap):
        depth_cap = (
            await session.scalar(
                select(GraphEdge.id)
                .where(
                    GraphEdge.snapshot_id == snapshot_id,
                    GraphEdge.source_id.in_(frontier),
                    GraphEdge.target_id.not_in(visited),
                    GraphEdge.relationship.in_(RELATIONSHIPS),
                )
                .limit(1)
            )
            is not None
        )
    return discovered, edges, node_cap, edge_cap, depth_cap


async def graph_chunks(
    session: AsyncSession, identity: Identity, nodes: dict[UUID, Walk]
) -> tuple[dict[UUID, tuple[Match, Walk]], bool]:
    if not nodes:
        return {}, False
    overlap = (
        func.least(GraphNode.end_line, SourceChunk.end_line)
        - func.greatest(GraphNode.start_line, SourceChunk.start_line)
        + 1
    )
    priority = func.row_number().over(
        partition_by=GraphNode.id,
        order_by=(
            case((GraphNode.kind == "module", 0), else_=overlap).desc(),
            SourceChunk.start_line,
            SourceChunk.stable_key,
        ),
    )
    choices = (
        select(
            GraphNode.id.label("node_id"),
            SourceChunk.id.label("chunk_id"),
            priority.label("priority"),
        )
        .join(
            SourceChunk,
            and_(
                SourceChunk.snapshot_id == GraphNode.snapshot_id,
                SourceChunk.source_file_id == GraphNode.source_file_id,
            ),
        )
        .where(
            GraphNode.snapshot_id == identity.snapshot_id,
            GraphNode.id.in_(nodes),
            SourceChunk.chunking_version == VERSION,
            (GraphNode.kind == "module")
            | and_(
                SourceChunk.start_line <= GraphNode.end_line,
                SourceChunk.end_line >= GraphNode.start_line,
            ),
        )
        .subquery()
    )
    rows = await session.execute(
        select(choices.c.node_id, choices.c.chunk_id).where(choices.c.priority == 1)
    )
    paths: dict[UUID, Walk] = {}
    for node, chunk in rows:
        walk = nodes[node]
        if chunk == walk.seed.chunk_id:
            continue
        previous = paths.get(chunk)
        if previous is None or path_order(walk) < path_order(previous):
            paths[chunk] = walk
    selected = sorted(paths, key=lambda chunk: (path_order(paths[chunk]), chunk))
    evidence = await session.execute(
        select(SourceChunk, SourceFile.path)
        .options(defer(SourceChunk.token_text), defer(SourceChunk.search_vector))
        .join(
            SourceFile,
            and_(
                SourceFile.snapshot_id == SourceChunk.snapshot_id,
                SourceFile.id == SourceChunk.source_file_id,
            ),
        )
        .where(
            SourceChunk.snapshot_id == identity.snapshot_id,
            SourceChunk.chunking_version == VERSION,
            SourceChunk.id.in_(selected[:MAX_EXPANDED]),
        )
    )
    return {
        chunk.id: (make_match(identity, chunk, path, 0, 0), paths[chunk.id])
        for chunk, path in evidence
    }, len(selected) > MAX_EXPANDED


def path_order(walk: Walk) -> tuple[Fraction, int, tuple[UUID, ...]]:
    return (
        -walk.contribution,
        walk.seed.rank,
        tuple(edge.edge_id for edge in walk.edges),
    )


def rank_results(
    baseline: list[HybridMatch], expanded: dict[UUID, tuple[Match, Walk]], limit: int
) -> list[GraphMatch]:
    seeds = {hit.chunk_id: hit for hit in baseline}
    evidence = {chunk_id: pair[0] for chunk_id, pair in expanded.items()} | seeds
    ranked = []
    for chunk_id, match in evidence.items():
        hybrid = seeds.get(chunk_id)
        path = expanded[chunk_id][1] if chunk_id in expanded else None
        contribution = path.contribution if path else Fraction()
        baseline_score = (
            rrf_score(hybrid.lexical_rank, hybrid.vector_rank) if hybrid else Fraction()
        )
        score = baseline_score + contribution
        channels: list[Literal["lexical", "vector", "graph"]] = []
        if hybrid:
            channels.extend(hybrid.channels)
        if path:
            channels.append("graph")
        result = GraphMatch(
            **match.model_dump(include=set(Match.model_fields) - {"score"}),
            score=float(score),
            hybrid_rank=hybrid.rank if hybrid else None,
            hybrid_score=hybrid.score if hybrid else None,
            graph_contribution=float(contribution),
            channels=channels,
            provenance=path.evidence() if path else None,
        )
        ranked.append((-score, result.path, result.start_line, chunk_id, result))
    ranked.sort(key=lambda entry: entry[:4])
    return [
        hit.model_copy(update={"rank": rank})
        for rank, (*_, hit) in enumerate(ranked[:limit], 1)
    ]


async def graph_search(
    session: AsyncSession,
    snapshot_id: UUID,
    query: str,
    limit: int,
    provider: EmbeddingProvider,
) -> GraphSearchResponse:
    async def require_analysis() -> str:
        return await analysis_stamp(session, snapshot_id)

    baseline = await hybrid_search(
        session,
        snapshot_id,
        query,
        2 * POOL_SIZE,
        provider,
        prerequisite=require_analysis,
    )
    seeds = baseline.results[:MAX_SEEDS]
    mapping = await seed_nodes(session, snapshot_id, seeds)
    starts: dict[UUID, Walk] = {}
    for seed in seeds:
        if (node := mapping.get(seed.chunk_id)) is not None:
            starts.setdefault(node, Walk(seed, (node,)))
    discovered, edge_count, node_cap, edge_cap, depth_cap = await walk_graph(
        session, snapshot_id, starts
    )
    expanded, chunk_cap = await graph_chunks(session, baseline, discovered)
    return GraphSearchResponse(
        **baseline.model_dump(exclude={"results"}),
        expansion=ExpansionPolicy(),
        traversal=TraversalStats(
            seed_count=len(seeds),
            mapped_seed_count=len(mapping),
            visited_nodes=len(starts) + len(discovered),
            traversed_edges=edge_count,
            expanded_chunks=len(expanded),
            depth_reached=max(
                (len(path.edges) for path in discovered.values()), default=0
            ),
            depth_limit_reached=depth_cap,
            node_limit_reached=node_cap,
            edge_limit_reached=edge_cap,
            chunk_limit_reached=chunk_cap,
            truncated=node_cap or edge_cap or chunk_cap or depth_cap,
        ),
        results=rank_results(baseline.results, expanded, limit),
    )
