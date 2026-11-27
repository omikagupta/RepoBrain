from datetime import datetime
from enum import StrEnum
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    Enum,
    FetchedValue,
    ForeignKey,
    String,
    Text,
    UniqueConstraint,
    func,
)
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
