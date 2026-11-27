from collections.abc import Sequence
from dataclasses import dataclass
from hashlib import sha256
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import defer

from repobrain.answers.models import Claim, Draft, Evidence
from repobrain.answers.provider import invalid_output, json_bytes
from repobrain.database.models import SourceChunk, SourceFile
from repobrain.graph.exploration import (
    ExplorationError,
    Identity,
    checked_path,
    source_permalink,
)
from repobrain.search.chunking import exact_lines
from repobrain.search.graph_enhanced import GraphMatch
from repobrain.search.service import Match

MAX_CANDIDATES = 20
MAX_EVIDENCE = 12
MAX_EVIDENCE_BYTES = 32 * 1024


@dataclass(frozen=True)
class Context:
    evidence: tuple[Evidence, ...]
    serialized: bytes
    truncated: bool


def evidence_error() -> ExplorationError:
    return ExplorationError(
        409, "invalid_source_evidence", "Stored source evidence is inconsistent"
    )


async def materialize(
    session: AsyncSession, identity: Identity, version: str, hits: Sequence[Match]
) -> list[Evidence]:
    if not hits:
        return []
    if len(hits) > MAX_CANDIDATES or any(
        (hit.snapshot_id, hit.repository, hit.commit_sha)
        != (identity.snapshot_id, identity.repository, identity.commit_sha)
        for hit in hits
    ):
        raise evidence_error()
    chunks = {
        chunk.id: chunk
        for chunk in await session.scalars(
            select(SourceChunk)
            .options(defer(SourceChunk.token_text), defer(SourceChunk.search_vector))
            .where(
                SourceChunk.snapshot_id == identity.snapshot_id,
                SourceChunk.chunking_version == version,
                SourceChunk.id.in_([hit.chunk_id for hit in hits]),
            )
        )
    }
    files = {
        source.id: source
        for source in await session.scalars(
            select(SourceFile).where(
                SourceFile.snapshot_id == identity.snapshot_id,
                SourceFile.id.in_({chunk.source_file_id for chunk in chunks.values()}),
            )
        )
    }
    source_lines: dict[UUID, list[str]] = {}
    evidence = []
    for hit in hits:
        chunk = chunks.get(hit.chunk_id)
        if chunk is None or chunk.source_file_id != hit.source_file_id:
            raise evidence_error()
        source = files.get(chunk.source_file_id)
        if source is None:
            raise evidence_error()
        if source.id not in source_lines:
            if sha256(source.content.encode()).hexdigest() != source.content_sha256:
                raise evidence_error()
            source_lines[source.id] = exact_lines(source.content)
        lines = source_lines[source.id]
        start, end = chunk.start_line, chunk.end_line
        if (
            not 1 <= start <= end <= len(lines)
            or chunk.content != "".join(lines[start - 1 : end])
            or sha256(chunk.content.encode()).hexdigest() != chunk.content_sha256
            or source.content_sha256 != chunk.source_sha256
            or (
                hit.path,
                hit.start_line,
                hit.end_line,
                hit.text,
                hit.source_sha256,
                hit.content_sha256,
            )
            != (
                source.path,
                start,
                end,
                chunk.content,
                source.content_sha256,
                chunk.content_sha256,
            )
        ):
            raise evidence_error()
        permalink = source_permalink(identity, checked_path(source.path), start, end)
        evidence.append(
            Evidence(
                **identity.model_dump(),
                citation_id="E1",
                chunk_id=chunk.id,
                source_file_id=source.id,
                path=source.path,
                start_line=start,
                end_line=end,
                text=chunk.content,
                source_sha256=source.content_sha256,
                content_sha256=chunk.content_sha256,
                permalink=permalink,
                rank=hit.rank,
                score=hit.score,
                provenance=hit.provenance if isinstance(hit, GraphMatch) else None,
            )
        )
    return evidence


def build_context(candidates: Sequence[Evidence]) -> Context:
    selected: list[Evidence] = []
    records: list[dict[str, object]] = []
    serialized = json_bytes({"evidence": records})
    for evidence in candidates:
        if len(selected) == MAX_EVIDENCE:
            break
        included = evidence.model_copy(update={"citation_id": f"E{len(selected) + 1}"})
        record: dict[str, object] = {
            "citation_id": included.citation_id,
            "path": included.path,
            "start_line": included.start_line,
            "end_line": included.end_line,
            "text": included.text,
        }
        if included.provenance is not None:
            record["relationships"] = [
                edge.relationship for edge in included.provenance.edges
            ]
        encoded = json_bytes({"evidence": [*records, record]})
        if len(encoded) > MAX_EVIDENCE_BYTES:
            continue
        records.append(record)
        selected.append(included)
        serialized = encoded
    return Context(tuple(selected), serialized, len(selected) < len(candidates))


def validate_citations(
    draft: Draft, context: Context, snapshot: Identity
) -> tuple[list[Claim], list[Evidence]]:
    claims = []
    cited: dict[str, Evidence] = {}
    by_id = {item.citation_id: item for item in context.evidence}
    for claim in draft.claims:
        ids = list(dict.fromkeys(claim.citations))
        for id_ in ids:
            item = by_id.get(id_)
            if item is None or (item.snapshot_id, item.repository, item.commit_sha) != (
                snapshot.snapshot_id,
                snapshot.repository,
                snapshot.commit_sha,
            ):
                raise invalid_output()
            cited.setdefault(id_, item)
        claims.append(claim.model_copy(update={"citations": ids}))
    return claims, list(cited.values())
