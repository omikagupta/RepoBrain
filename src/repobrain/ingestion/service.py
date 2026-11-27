import asyncio
import logging
from datetime import datetime, timedelta
from uuid import UUID

import httpx
from pydantic import BaseModel
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repobrain.database.models import (
    IngestionState,
    Repository,
    RepositorySnapshot,
    SourceFile,
)
from repobrain.ingestion.github import Commit, GitHub, IngestionError, PythonFile
from repobrain.settings import Settings

logger = logging.getLogger("repobrain.ingestion")
ACTIVE = (IngestionState.PENDING, IngestionState.RUNNING)


class Failure(BaseModel):
    code: str
    message: str


class SnapshotStatus(BaseModel):
    snapshot_id: UUID
    repository: str
    commit_sha: str
    state: IngestionState
    file_count: int
    error: Failure | None = None


class IngestionService:
    def __init__(
        self,
        sessions: async_sessionmaker[AsyncSession],
        client: httpx.AsyncClient,
        settings: Settings,
    ) -> None:
        self.sessions = sessions
        self.client = client
        self.settings = settings
        self.active = 0
        self.tasks: set[asyncio.Task[None]] = set()

    async def close(self) -> None:
        tasks = tuple(self.tasks)
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)

    async def expire(self, session: AsyncSession, snapshot_id: UUID) -> None:
        deadline = func.statement_timestamp() - timedelta(
            seconds=self.settings.ingestion_timeout + 15
        )
        await session.execute(
            update(RepositorySnapshot)
            .where(
                RepositorySnapshot.id == snapshot_id,
                RepositorySnapshot.ingestion_state.in_(ACTIVE),
                RepositorySnapshot.updated_at < deadline,
            )
            .values(ingestion_state=IngestionState.FAILED)
        )

    async def status(self, snapshot_id: UUID) -> SnapshotStatus:
        async with self.sessions.begin() as session:
            await self.expire(session, snapshot_id)
            snapshot = await session.get(RepositorySnapshot, snapshot_id)
            if snapshot is None:
                raise IngestionError(
                    404, "snapshot_not_found", "Ingestion snapshot not found"
                )
            repository = await session.get_one(Repository, snapshot.repository_id)
            state = snapshot.ingestion_state
            count = 0
            if state == IngestionState.COMPLETED:
                count = (
                    await session.scalar(
                        select(func.count())
                        .select_from(SourceFile)
                        .where(SourceFile.snapshot_id == snapshot_id)
                    )
                    or 0
                )
            return SnapshotStatus(
                snapshot_id=snapshot.id,
                repository=f"{repository.owner}/{repository.name}",
                commit_sha=snapshot.commit_sha,
                state=state,
                file_count=count,
                error=Failure(
                    code="ingestion_failed", message="Ingestion did not complete"
                )
                if state == IngestionState.FAILED
                else None,
            )

    async def prepare(self, commit: Commit) -> tuple[UUID, datetime | None]:
        owner, name = commit.repository.split("/")
        async with self.sessions.begin() as session:
            await session.execute(
                insert(Repository)
                .values(owner=owner, name=name)
                .on_conflict_do_nothing(index_elements=["owner", "name"])
            )
            repository_id = (
                await session.execute(
                    select(Repository.id).where(
                        Repository.owner == owner, Repository.name == name
                    )
                )
            ).scalar_one()
            new = await session.scalar(
                insert(RepositorySnapshot)
                .values(repository_id=repository_id, commit_sha=commit.sha)
                .on_conflict_do_nothing(index_elements=["repository_id", "commit_sha"])
                .returning(RepositorySnapshot.id)
            )
            snapshot_id = (
                new
                if new is not None
                else (
                    await session.execute(
                        select(RepositorySnapshot.id).where(
                            RepositorySnapshot.repository_id == repository_id,
                            RepositorySnapshot.commit_sha == commit.sha,
                        )
                    )
                ).scalar_one()
            )
            await self.expire(session, snapshot_id)
            snapshot = (
                await session.execute(
                    select(RepositorySnapshot)
                    .where(RepositorySnapshot.id == snapshot_id)
                    .with_for_update()
                )
            ).scalar_one()
            if snapshot.ingestion_state == IngestionState.FAILED:
                snapshot.ingestion_state = IngestionState.PENDING
                await session.flush()
                await session.refresh(snapshot, ["updated_at"])
                return snapshot_id, snapshot.updated_at
            return snapshot_id, snapshot.updated_at if new is not None else None

    async def submit(
        self, repository: str, ref: str | None, request_id: str
    ) -> SnapshotStatus:
        if self.active >= self.settings.ingestion_concurrency:
            raise IngestionError(
                429, "ingestion_busy", "Ingestion capacity is full; retry later"
            )
        self.active += 1
        scheduled = False
        try:
            github = GitHub(self.client, self.settings)
            async with asyncio.timeout(self.settings.ingestion_timeout):
                commit = await github.resolve(repository, ref)
                snapshot_id, pending = await self.prepare(commit)
            if pending is not None:
                task = asyncio.create_task(
                    self.run(github, commit, snapshot_id, pending, request_id)
                )
                self.tasks.add(task)
                task.add_done_callback(self.tasks.discard)
                scheduled = True
            return await self.status(snapshot_id)
        except TimeoutError:
            raise IngestionError(
                504, "ingestion_timeout", "Ingestion request timed out"
            ) from None
        finally:
            if not scheduled:
                self.active -= 1

    async def transition(
        self,
        session: AsyncSession,
        snapshot_id: UUID,
        token: datetime,
        previous: IngestionState,
        next_state: IngestionState,
    ) -> datetime | None:
        return await session.scalar(
            update(RepositorySnapshot)
            .where(
                RepositorySnapshot.id == snapshot_id,
                RepositorySnapshot.ingestion_state == previous,
                RepositorySnapshot.updated_at == token,
            )
            .values(ingestion_state=next_state)
            .returning(RepositorySnapshot.updated_at)
        )

    async def complete(
        self, snapshot_id: UUID, token: datetime, files: list[PythonFile]
    ) -> None:
        async with self.sessions.begin() as session:
            updated = await self.transition(
                session,
                snapshot_id,
                token,
                IngestionState.RUNNING,
                IngestionState.COMPLETED,
            )
            if updated is not None:
                session.add_all(
                    SourceFile(
                        snapshot_id=snapshot_id,
                        path=file.path,
                        content=file.content,
                        content_sha256=file.content_sha256,
                        line_count=file.line_count,
                        language="python",
                    )
                    for file in files
                )

    async def run(
        self,
        github: GitHub,
        commit: Commit,
        snapshot_id: UUID,
        token: datetime,
        request_id: str,
    ) -> None:
        fields = {"request_id": request_id, "snapshot_id": str(snapshot_id)}
        state = IngestionState.PENDING
        try:
            async with asyncio.timeout(self.settings.ingestion_timeout):
                async with self.sessions.begin() as session:
                    running = await self.transition(
                        session, snapshot_id, token, state, IngestionState.RUNNING
                    )
                if running is None:
                    return
                state, token = IngestionState.RUNNING, running
                files = await github.collect(commit)
                await self.complete(snapshot_id, token, files)
        except (Exception, asyncio.CancelledError) as exc:
            code = exc.code if isinstance(exc, IngestionError) else type(exc).__name__
            logger.warning(
                "ingestion_failed", extra={"event_fields": {**fields, "reason": code}}
            )
            try:
                async with asyncio.timeout(5):
                    async with self.sessions.begin() as session:
                        await self.transition(
                            session, snapshot_id, token, state, IngestionState.FAILED
                        )
            except Exception:
                logger.error(
                    "ingestion_state_write_failed", extra={"event_fields": fields}
                )
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            self.active -= 1
