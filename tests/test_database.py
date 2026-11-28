from collections.abc import AsyncIterator
from hashlib import sha256
from uuid import uuid4

import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.database.models import (
    Base,
    IngestionState,
    Repository,
    RepositorySnapshot,
    SourceFile,
)
from repobrain.settings import Settings

pytestmark = pytest.mark.postgres


@pytest_asyncio.fixture
async def sessions(
    migrated_database: Settings,
) -> AsyncIterator[async_sessionmaker[AsyncSession]]:
    engine = create_database_engine(migrated_database)
    try:
        yield create_session_factory(engine)
    finally:
        await engine.dispose()


async def insert_snapshot(session: AsyncSession) -> RepositorySnapshot:
    repository = Repository(owner="repobrain", name=f"sample-{uuid4().hex}")
    session.add(repository)
    await session.flush()
    snapshot = RepositorySnapshot(repository_id=repository.id, commit_sha="a" * 40)
    session.add(snapshot)
    await session.flush()
    return snapshot


def make_file(snapshot: RepositorySnapshot, path: str = "src/main.py") -> SourceFile:
    content = "print('hello')\n"
    return SourceFile(
        snapshot_id=snapshot.id,
        path=path,
        content=content,
        content_sha256=sha256(content.encode()).hexdigest(),
        language="python",
        line_count=1,
    )


@pytest.mark.asyncio
async def test_migration_upgrade(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions() as session:
        version = await session.scalar(text("SELECT version_num FROM alembic_version"))
        vector = await session.scalar(
            text("SELECT extversion FROM pg_extension WHERE extname = 'vector'")
        )
    assert version == "0007_hosted_cache"
    assert vector


@pytest.mark.asyncio
async def test_persistence_crud(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions.begin() as session:
        snapshot = await insert_snapshot(session)
        source = make_file(snapshot)
        session.add(source)
        await session.flush()
        assert snapshot.ingestion_state is IngestionState.PENDING
        assert snapshot.created_at.tzinfo is not None

    async with sessions.begin() as session:
        saved = await session.scalar(
            select(SourceFile).where(
                SourceFile.snapshot_id == snapshot.id, SourceFile.path == source.path
            )
        )
        assert saved is not None
        assert saved.content == source.content
        assert saved.content_sha256 == source.content_sha256
        assert saved.language == "python"
        assert saved.line_count == 1
        saved_snapshot = await session.get(RepositorySnapshot, snapshot.id)
        assert saved_snapshot is not None
        saved_snapshot.ingestion_state = IngestionState.COMPLETED

    async with sessions.begin() as session:
        saved_snapshot = await session.get(RepositorySnapshot, snapshot.id)
        assert saved_snapshot is not None
        assert saved_snapshot.ingestion_state is IngestionState.COMPLETED
        assert saved_snapshot.updated_at > saved_snapshot.created_at
        repository = await session.get(Repository, snapshot.repository_id)
        assert repository is not None
        await session.delete(repository)

    async with sessions() as session:
        assert await session.get(Repository, snapshot.repository_id) is None
        assert await session.get(RepositorySnapshot, snapshot.id) is None
        assert await session.get(SourceFile, source.id) is None


async def assert_insert_rejected(
    session: AsyncSession, row: Base, sqlstate: str
) -> None:
    with pytest.raises(IntegrityError) as error:
        async with session.begin_nested():
            session.add(row)
            await session.flush()
    assert getattr(error.value.orig, "sqlstate", None) == sqlstate


@pytest.mark.asyncio
async def test_unique_constraints(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions.begin() as session:
        snapshot = await insert_snapshot(session)
        repository = await session.get(Repository, snapshot.repository_id)
        assert repository is not None
        session.add(make_file(snapshot))
        await session.flush()
        await assert_insert_rejected(
            session, Repository(owner=repository.owner, name=repository.name), "23505"
        )
        await assert_insert_rejected(
            session,
            RepositorySnapshot(
                repository_id=repository.id, commit_sha=snapshot.commit_sha
            ),
            "23505",
        )
        await assert_insert_rejected(session, make_file(snapshot), "23505")


@pytest.mark.asyncio
async def test_foreign_keys(sessions: async_sessionmaker[AsyncSession]) -> None:
    async with sessions.begin() as session:
        orphan = RepositorySnapshot(
            id=uuid4(), repository_id=uuid4(), commit_sha="a" * 40
        )
        await assert_insert_rejected(session, orphan, "23503")
        await assert_insert_rejected(session, make_file(orphan), "23503")


@pytest.mark.asyncio
async def test_path_and_snapshot_identity_constraints(
    sessions: async_sessionmaker[AsyncSession],
) -> None:
    async with sessions.begin() as session:
        snapshot = await insert_snapshot(session)
        await assert_insert_rejected(
            session, make_file(snapshot, "src/../main.py"), "23514"
        )
        with pytest.raises(IntegrityError) as error:
            async with session.begin_nested():
                snapshot.commit_sha = "b" * 40
                await session.flush()
        assert getattr(error.value.orig, "sqlstate", None) == "23514"
