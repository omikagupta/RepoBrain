import base64
import binascii
import hmac
import json
import re
import secrets
from dataclasses import dataclass
from typing import Literal
from urllib.parse import quote
from uuid import UUID

from pydantic import BaseModel, Field
from sqlalchemy import Select, and_, case, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from repobrain.database.models import (
    GraphAnalysis,
    GraphEdge,
    GraphNode,
    IngestionState,
    Repository,
    RepositorySnapshot,
    SourceFile,
)
from repobrain.ingestion.github import IngestionError, canonical_repository, safe_path

Relationship = Literal["CONTAINS", "IMPORTS", "IMPORTS_SYMBOL"]
NodeKind = Literal["module", "class", "function", "method"]
Direction = Literal["incoming", "outgoing", "both"]
RELATIONSHIPS: tuple[Relationship, ...] = ("CONTAINS", "IMPORTS", "IMPORTS_SYMBOL")
MAX_NEIGHBOR_NODES = 100
MAX_NEIGHBOR_EDGES = 200
MAX_SOURCE_LINES = 200
MAX_SOURCE_BYTES = 64 * 1024
MAX_STORED_BYTES = 1024**2
CURSOR_KEY = secrets.token_bytes(32)


class ExplorationError(Exception):
    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


class Identity(BaseModel):
    snapshot_id: UUID
    repository: str
    commit_sha: str


class Summary(Identity):
    analyzed_files: int
    node_count: int
    edge_count: int
    diagnostic_count: int
    supported_relationships: tuple[Relationship, ...] = RELATIONSHIPS


class NodeView(BaseModel):
    id: UUID
    snapshot_id: UUID
    kind: NodeKind
    qualified_name: str
    path: str
    start_line: int | None
    end_line: int | None
    is_async: bool


class EdgeView(BaseModel):
    model_config = {"from_attributes": True}

    id: UUID
    snapshot_id: UUID
    source_id: UUID
    target_id: UUID
    relationship: Relationship
    line: int | None
    column: int | None
    provenance: str


class Page[T](BaseModel):
    items: list[T]
    next_cursor: str | None


class Pagination(BaseModel):
    limit: int = Field(50, ge=1, le=100)
    cursor: str | None = Field(None, min_length=1, max_length=256)


class NodeFilters(Pagination):
    kind: NodeKind | None = None
    qualified_name_prefix: str | None = Field(None, min_length=1, max_length=256)
    path: str | None = Field(None, min_length=1, max_length=1024)


class EdgeFilters(Pagination):
    relationship: Relationship | None = None
    source_id: UUID | None = None
    target_id: UUID | None = None


class Neighborhood(BaseModel):
    snapshot_id: UUID
    center_node_id: UUID
    depth: Literal[1, 2]
    nodes: list[NodeView]
    edges: list[EdgeView]
    truncated: bool


class LineRange(BaseModel):
    start_line: int | None
    end_line: int | None


class SourceLine(BaseModel):
    line_number: int
    text: str


class SourceView(Identity):
    path: str
    requested_range: LineRange
    actual_range: LineRange
    lines: list[SourceLine]
    content_sha256: str
    permalink: str


@dataclass(frozen=True)
class Snapshot:
    identity: Identity
    state: IngestionState
    counts: tuple[int, int, int, int] | None


async def load_snapshot(session: AsyncSession, snapshot_id: UUID) -> Snapshot:
    row = (
        await session.execute(
            select(
                Repository.owner,
                Repository.name,
                RepositorySnapshot.commit_sha,
                RepositorySnapshot.ingestion_state,
                GraphAnalysis.analyzed_files,
                GraphAnalysis.node_count,
                GraphAnalysis.edge_count,
                func.jsonb_array_length(GraphAnalysis.diagnostics),
            )
            .select_from(RepositorySnapshot)
            .join(Repository, Repository.id == RepositorySnapshot.repository_id)
            .outerjoin(
                GraphAnalysis, GraphAnalysis.snapshot_id == RepositorySnapshot.id
            )
            .where(RepositorySnapshot.id == snapshot_id)
        )
    ).one_or_none()
    if row is None:
        raise ExplorationError(404, "snapshot_not_found", "Snapshot not found")
    owner, name, sha, state, files, nodes, edges, diagnostics = row
    return Snapshot(
        Identity(snapshot_id=snapshot_id, repository=f"{owner}/{name}", commit_sha=sha),
        state,
        None if files is None else (files, nodes, edges, diagnostics),
    )


def require_graph(snapshot: Snapshot) -> tuple[int, int, int, int]:
    if snapshot.counts is None:
        raise ExplorationError(
            409, "graph_not_analyzed", "Snapshot has no completed graph"
        )
    return snapshot.counts


def page_context(resource: str, snapshot_id: UUID, filters: Pagination) -> bytes:
    fields = filters.model_dump(mode="json", exclude={"limit", "cursor"})
    return json.dumps([resource, str(snapshot_id), fields], sort_keys=True).encode()


def encode_cursor(context: bytes, key: str) -> str:
    encoded = key.encode("ascii")
    tag = hmac.digest(CURSOR_KEY, context + b"\0" + encoded, "sha256")
    return base64.urlsafe_b64encode(encoded + tag).rstrip(b"=").decode("ascii")


def decode_cursor(context: bytes, cursor: str | None) -> str | None:
    if cursor is None:
        return None
    try:
        if not re.fullmatch(r"[A-Za-z0-9_-]{128}", cursor):
            raise ValueError
        raw = base64.b64decode(cursor, altchars=b"-_", validate=True)
        key = raw[:64].decode("ascii")
        if not re.fullmatch(r"[a-f0-9]{64}", key) or not hmac.compare_digest(
            encode_cursor(context, key), cursor
        ):
            raise ValueError
        return key
    except (ValueError, binascii.Error):
        raise ExplorationError(
            422, "invalid_cursor", "Cursor is invalid for this query"
        ) from None


def checked_path(path: str) -> str:
    try:
        return safe_path(path)
    except IngestionError:
        raise ExplorationError(
            422, "invalid_path", "Expected a safe relative file path"
        ) from None


def node_query(snapshot_id: UUID) -> Select[tuple[GraphNode, str]]:
    return (
        select(GraphNode, SourceFile.path)
        .join(
            SourceFile,
            and_(
                SourceFile.id == GraphNode.source_file_id,
                SourceFile.snapshot_id == GraphNode.snapshot_id,
            ),
        )
        .where(GraphNode.snapshot_id == snapshot_id)
    )


def node_view(node: GraphNode, path: str) -> NodeView:
    return NodeView.model_validate(
        {
            "id": node.id,
            "snapshot_id": node.snapshot_id,
            "kind": node.kind,
            "qualified_name": node.qualified_name,
            "path": path,
            "start_line": node.start_line,
            "end_line": node.end_line,
            "is_async": node.is_async,
        }
    )


async def list_nodes(
    session: AsyncSession, snapshot_id: UUID, filters: NodeFilters
) -> Page[NodeView]:
    context = page_context("nodes", snapshot_id, filters)
    after = decode_cursor(context, filters.cursor)
    stmt = node_query(snapshot_id)
    if filters.kind is not None:
        stmt = stmt.where(GraphNode.kind == filters.kind)
    if filters.qualified_name_prefix is not None:
        prefix = filters.qualified_name_prefix
        if "\x00" in prefix:
            raise ExplorationError(
                422, "invalid_prefix", "Invalid qualified name prefix"
            )
        stmt = stmt.where(GraphNode.qualified_name.startswith(prefix, autoescape=True))
    if filters.path is not None:
        stmt = stmt.where(SourceFile.path == checked_path(filters.path))
    if after is not None:
        stmt = stmt.where(GraphNode.stable_key > after)
    rows = (
        await session.execute(
            stmt.order_by(GraphNode.stable_key).limit(filters.limit + 1)
        )
    ).all()
    page = rows[: filters.limit]
    return Page(
        items=[node_view(node, path) for node, path in page],
        next_cursor=encode_cursor(context, page[-1][0].stable_key)
        if len(rows) > filters.limit
        else None,
    )


async def list_edges(
    session: AsyncSession, snapshot_id: UUID, filters: EdgeFilters
) -> Page[EdgeView]:
    context = page_context("edges", snapshot_id, filters)
    after = decode_cursor(context, filters.cursor)
    stmt = select(GraphEdge).where(GraphEdge.snapshot_id == snapshot_id)
    if filters.relationship is not None:
        stmt = stmt.where(GraphEdge.relationship == filters.relationship)
    if filters.source_id is not None:
        stmt = stmt.where(GraphEdge.source_id == filters.source_id)
    if filters.target_id is not None:
        stmt = stmt.where(GraphEdge.target_id == filters.target_id)
    if after is not None:
        stmt = stmt.where(GraphEdge.stable_key > after)
    rows = (
        await session.scalars(
            stmt.order_by(GraphEdge.stable_key).limit(filters.limit + 1)
        )
    ).all()
    page = rows[: filters.limit]
    return Page(
        items=[EdgeView.model_validate(edge) for edge in page],
        next_cursor=encode_cursor(context, page[-1].stable_key)
        if len(rows) > filters.limit
        else None,
    )


async def neighborhood(
    session: AsyncSession,
    snapshot_id: UUID,
    center: UUID,
    direction: Direction,
    depth: Literal[1, 2],
    relationships: list[Relationship] | None,
) -> Neighborhood:
    if (
        await session.scalar(
            select(GraphNode.id).where(
                GraphNode.snapshot_id == snapshot_id,
                GraphNode.id == center,
            )
        )
        is None
    ):
        raise ExplorationError(404, "node_not_found", "Graph node not found")
    visited = frontier = {center}
    edges: dict[UUID, GraphEdge] = {}
    truncated = False
    for _ in range(depth):
        if not frontier or truncated:
            break
        predicates = []
        if direction in ("outgoing", "both"):
            predicates.append(GraphEdge.source_id.in_(frontier))
        if direction in ("incoming", "both"):
            predicates.append(GraphEdge.target_id.in_(frontier))
        stmt = select(GraphEdge).where(
            GraphEdge.snapshot_id == snapshot_id, or_(*predicates)
        )
        if relationships:
            stmt = stmt.where(GraphEdge.relationship.in_(relationships))
        if edges:
            stmt = stmt.where(GraphEdge.id.not_in(edges))
        rows = await session.scalars(
            stmt.order_by(GraphEdge.stable_key).limit(
                MAX_NEIGHBOR_EDGES - len(edges) + 1
            )
        )
        next_frontier: set[UUID] = set()
        for edge in rows:
            new_nodes = {edge.source_id, edge.target_id} - visited
            if (
                len(edges) >= MAX_NEIGHBOR_EDGES
                or len(visited | new_nodes) > MAX_NEIGHBOR_NODES
            ):
                truncated = True
                break
            edges[edge.id] = edge
            visited = visited | new_nodes
            next_frontier.update(new_nodes)
        frontier = next_frontier
    nodes = (
        await session.execute(
            node_query(snapshot_id)
            .where(GraphNode.id.in_(visited))
            .order_by(GraphNode.stable_key)
        )
    ).all()
    return Neighborhood(
        snapshot_id=snapshot_id,
        center_node_id=center,
        depth=depth,
        truncated=truncated,
        nodes=[node_view(node, path) for node, path in nodes],
        edges=[
            EdgeView.model_validate(edge)
            for edge in sorted(edges.values(), key=lambda edge: edge.stable_key)
        ],
    )


def slice_source(content: str, start: int, end: int) -> list[SourceLine]:
    lines = []
    size = 0
    for number, match in enumerate(
        re.finditer(r"([^\r\n]*)(?:\r\n|\r|\n|$)", content), 1
    ):
        if not match[0] or number > end:
            break
        if number < start:
            continue
        line = SourceLine(line_number=number, text=match[1])
        size += len(line.model_dump_json().encode()) + 1
        if size > MAX_SOURCE_BYTES:
            raise ExplorationError(
                422, "source_window_too_large", "Source window exceeds byte limit"
            )
        lines.append(line)
    if content and not lines:
        raise ExplorationError(
            422, "invalid_line_range", "Start line is past end of file"
        )
    return lines


def source_permalink(
    identity: Identity, path: str, actual_start: int | None, actual_end: int | None
) -> str:
    try:
        name = canonical_repository(identity.repository)
    except ValueError:
        raise ExplorationError(
            500, "invalid_snapshot_identity", "Invalid stored snapshot identity"
        ) from None
    if not re.fullmatch(r"[a-f0-9]{40}", identity.commit_sha):
        raise ExplorationError(
            500, "invalid_snapshot_identity", "Invalid stored snapshot identity"
        )
    permalink = (
        f"https://github.com/{name}/blob/{identity.commit_sha}/{quote(path, safe='/')}"
    )
    if actual_start is not None:
        permalink += (
            f"#L{actual_start}"
            if actual_start == actual_end
            else f"#L{actual_start}-L{actual_end}"
        )
    return permalink


async def read_source(
    session: AsyncSession,
    snapshot: Snapshot,
    path: str,
    start_line: int | None,
    end_line: int | None,
) -> SourceView:
    path = checked_path(path)
    start = start_line or 1
    end = end_line if end_line is not None else start + MAX_SOURCE_LINES - 1
    if end < start or end - start >= MAX_SOURCE_LINES:
        raise ExplorationError(
            422, "invalid_line_range", "Expected an ordered window of up to 200 lines"
        )
    if snapshot.state != IngestionState.COMPLETED:
        raise ExplorationError(
            409, "snapshot_incomplete", "Snapshot ingestion is incomplete"
        )
    identity = snapshot.identity
    row = (
        await session.execute(
            select(
                SourceFile.content_sha256,
                case(
                    (
                        func.octet_length(SourceFile.content) <= MAX_STORED_BYTES,
                        SourceFile.content,
                    )
                ),
            ).where(
                SourceFile.snapshot_id == identity.snapshot_id, SourceFile.path == path
            )
        )
    ).one_or_none()
    if row is None:
        raise ExplorationError(404, "source_not_found", "Source file not found")
    digest, content = row
    if content is None:
        raise ExplorationError(
            422, "source_file_too_large", "Stored source exceeds byte limit"
        )
    lines = slice_source(content, start, end)
    actual_start = lines[0].line_number if lines else None
    actual_end = lines[-1].line_number if lines else None
    permalink = source_permalink(identity, path, actual_start, actual_end)
    return SourceView(
        **identity.model_dump(),
        path=path,
        content_sha256=digest,
        permalink=permalink,
        requested_range=LineRange(start_line=start_line, end_line=end_line),
        actual_range=LineRange(start_line=actual_start, end_line=actual_end),
        lines=lines,
    )
