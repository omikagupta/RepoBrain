from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from pgvector.sqlalchemy import VECTOR
from sqlalchemy import (
    CheckConstraint,
    Computed,
    DateTime,
    Enum,
    FetchedValue,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB, TSVECTOR
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class IngestionState(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


class Repository(Base):
    __tablename__ = "repositories"
    __table_args__ = (
        UniqueConstraint("owner", "name", name="uq_repositories_owner_name"),
        CheckConstraint("owner ~ '^[a-z0-9_-]+$'", name="ck_repositories_owner"),
        CheckConstraint("name ~ '^[a-z0-9_.-]+$'", name="ck_repositories_name"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    owner: Mapped[str] = mapped_column(Text)
    name: Mapped[str] = mapped_column(Text)


class RepositorySnapshot(Base):
    __tablename__ = "repository_snapshots"
    __table_args__ = (
        UniqueConstraint(
            "repository_id", "commit_sha", name="uq_snapshots_repository_commit"
        ),
        CheckConstraint(
            "commit_sha ~ '^[0-9a-f]{40}$'", name="ck_snapshots_commit_sha"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    repository_id: Mapped[UUID] = mapped_column(
        ForeignKey("repositories.id", ondelete="CASCADE")
    )
    commit_sha: Mapped[str] = mapped_column(String(40))
    ingestion_state: Mapped[IngestionState] = mapped_column(
        Enum(
            IngestionState,
            values_callable=lambda states: [state.value for state in states],
            name="ck_snapshots_ingestion_state",
            native_enum=False,
            create_constraint=True,
            validate_strings=True,
        ),
        server_default=IngestionState.PENDING.value,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        server_onupdate=FetchedValue(),
    )


class SourceFile(Base):
    __tablename__ = "source_files"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "id", name="uq_source_files_snapshot_id"),
        UniqueConstraint("snapshot_id", "path", name="uq_source_files_snapshot_path"),
        CheckConstraint(
            "path <> '' AND path !~ '(^/|/$|//|(^|/)[.]{1,2}(/|$)|^[A-Za-z]:)' "
            "AND strpos(path, chr(92)) = 0",
            name="ck_source_files_relative_path",
        ),
        CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_source_files_sha256"
        ),
        CheckConstraint("btrim(language) <> ''", name="ck_source_files_language"),
        CheckConstraint("line_count >= 0", name="ck_source_files_line_count"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True, default=uuid4)
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE")
    )
    path: Mapped[str] = mapped_column(Text)
    content_sha256: Mapped[str] = mapped_column(String(64))
    language: Mapped[str] = mapped_column(Text)
    line_count: Mapped[int]
    content: Mapped[str] = mapped_column(Text)


class GraphAnalysis(Base):
    __tablename__ = "graph_analyses"

    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), primary_key=True
    )
    analyzed_files: Mapped[int]
    node_count: Mapped[int]
    edge_count: Mapped[int]
    diagnostics: Mapped[list[dict[str, str | int | None]]] = mapped_column(JSONB)


class GraphNode(Base):
    __tablename__ = "graph_nodes"
    __table_args__ = (
        UniqueConstraint("snapshot_id", "id", name="uq_graph_nodes_snapshot_id"),
        UniqueConstraint(
            "snapshot_id", "stable_key", name="uq_graph_nodes_snapshot_key"
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "source_file_id"],
            ["source_files.snapshot_id", "source_files.id"],
            name="fk_graph_nodes_source_file",
            ondelete="CASCADE",
        ),
        Index("ix_graph_nodes_snapshot_file", "snapshot_id", "source_file_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("graph_analyses.snapshot_id", ondelete="CASCADE")
    )
    source_file_id: Mapped[UUID]
    stable_key: Mapped[str] = mapped_column(String(64))
    kind: Mapped[str] = mapped_column(String(24))
    qualified_name: Mapped[str] = mapped_column(Text)
    start_line: Mapped[int | None]
    end_line: Mapped[int | None]
    is_async: Mapped[bool]


class GraphEdge(Base):
    __tablename__ = "graph_edges"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id", "stable_key", name="uq_graph_edges_snapshot_key"
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "source_id"],
            ["graph_nodes.snapshot_id", "graph_nodes.id"],
            name="fk_graph_edges_source_node",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "target_id"],
            ["graph_nodes.snapshot_id", "graph_nodes.id"],
            name="fk_graph_edges_target_node",
            ondelete="CASCADE",
        ),
        Index("ix_graph_edges_snapshot_source", "snapshot_id", "source_id"),
        Index("ix_graph_edges_snapshot_target", "snapshot_id", "target_id"),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID]
    source_id: Mapped[UUID]
    target_id: Mapped[UUID]
    stable_key: Mapped[str] = mapped_column(String(64))
    relationship: Mapped[str] = mapped_column(String(24))
    line: Mapped[int | None]
    column: Mapped[int | None]
    provenance: Mapped[str] = mapped_column(Text)


class SearchIndex(Base):
    __tablename__ = "search_indexes"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id", "chunking_version", name="uq_search_index_version"
        ),
    )

    snapshot_id: Mapped[UUID] = mapped_column(
        ForeignKey("repository_snapshots.id", ondelete="CASCADE"), primary_key=True
    )
    chunking_version: Mapped[str] = mapped_column(String(24))
    chunk_count: Mapped[int]
    indexed_files: Mapped[int]
    indexed_bytes: Mapped[int]
    built_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class SourceChunk(Base):
    __tablename__ = "source_chunks"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id", "chunking_version", "id", name="uq_source_chunks_version_id"
        ),
        UniqueConstraint(
            "snapshot_id", "stable_key", name="uq_source_chunks_snapshot_key"
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "chunking_version"],
            ["search_indexes.snapshot_id", "search_indexes.chunking_version"],
            name="fk_source_chunks_search_index",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "source_file_id"],
            ["source_files.snapshot_id", "source_files.id"],
            name="fk_source_chunks_source_file",
        ),
        CheckConstraint(
            "start_line >= 1 AND end_line >= start_line", name="ck_source_chunks_range"
        ),
        Index(
            "ix_source_chunks_snapshot_file",
            "snapshot_id",
            "source_file_id",
            "start_line",
        ),
        Index(
            "ix_source_chunks_search_vector", "search_vector", postgresql_using="gin"
        ),
    )

    id: Mapped[UUID] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID]
    chunking_version: Mapped[str] = mapped_column(String(24))
    source_file_id: Mapped[UUID]
    stable_key: Mapped[str] = mapped_column(String(64))
    start_line: Mapped[int]
    end_line: Mapped[int]
    content: Mapped[str] = mapped_column(Text)
    source_sha256: Mapped[str] = mapped_column(String(64))
    content_sha256: Mapped[str] = mapped_column(String(64))
    token_text: Mapped[str] = mapped_column(Text)
    search_vector: Mapped[str] = mapped_column(
        TSVECTOR,
        Computed("to_tsvector('simple'::regconfig, token_text)", persisted=True),
    )


class VectorIndex(Base):
    __tablename__ = "vector_indexes"
    __table_args__ = (
        UniqueConstraint(
            "snapshot_id",
            "chunking_version",
            "vector_version",
            name="uq_vector_indexes_version",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "chunking_version"],
            ["search_indexes.snapshot_id", "search_indexes.chunking_version"],
            name="fk_vector_indexes_lexical_index",
            ondelete="CASCADE",
        ),
        CheckConstraint("dimension = 768", name="ck_vector_indexes_dimension"),
    )

    snapshot_id: Mapped[UUID] = mapped_column(primary_key=True)
    chunking_version: Mapped[str] = mapped_column(String(24))
    vector_version: Mapped[str] = mapped_column(String(24))
    model_id: Mapped[str] = mapped_column(Text)
    model_revision: Mapped[str] = mapped_column(Text)
    dimension: Mapped[int]
    encoding_policy: Mapped[str] = mapped_column(Text)
    chunk_count: Mapped[int]
    completed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class ChunkEmbedding(Base):
    __tablename__ = "chunk_embeddings"
    __table_args__ = (
        ForeignKeyConstraint(
            ["snapshot_id", "chunking_version", "vector_version"],
            [
                "vector_indexes.snapshot_id",
                "vector_indexes.chunking_version",
                "vector_indexes.vector_version",
            ],
            name="fk_chunk_embeddings_vector_index",
            ondelete="CASCADE",
        ),
        ForeignKeyConstraint(
            ["snapshot_id", "chunking_version", "chunk_id"],
            [
                "source_chunks.snapshot_id",
                "source_chunks.chunking_version",
                "source_chunks.id",
            ],
            name="fk_chunk_embeddings_source_chunk",
        ),
        Index("ix_chunk_embeddings_snapshot_version", "snapshot_id", "vector_version"),
    )

    chunk_id: Mapped[UUID] = mapped_column(primary_key=True)
    snapshot_id: Mapped[UUID]
    chunking_version: Mapped[str] = mapped_column(String(24))
    vector_version: Mapped[str] = mapped_column(String(24))
    embedding: Mapped[list[float]] = mapped_column(VECTOR(768))
