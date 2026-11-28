import asyncio
import logging
from datetime import datetime, timedelta
from time import monotonic
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
    Workspace,
    WorkspaceSnapshot,
)
from repobrain.ingestion.github import Commit, GitHub, IngestionError, PythonFile
from repobrain.quotas import check_repository, release, reserve
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
        self.github_resume = 0.0

    def note_upstream(self, error: IngestionError) -> None:
        if error.code == "github_rate_limited" and error.retry_after is not None:
            self.github_resume = max(
                self.github_resume, monotonic() + error.retry_after
            )

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

    async def prepare(
        self, commit: Commit, workspace: tuple[UUID, int] | None = None
    ) -> tuple[UUID, datetime | None]:
        owner, name = commit.repository.split("/")
        async with self.sessions.begin() as session:
            if workspace is not None:
                owner_workspace = await session.get(
                    Workspace, workspace[0], with_for_update=True
                )
                if owner_workspace is None or owner_workspace.revision != workspace[1]:
                    raise IngestionError(
                        409, "workspace_changed", "Retry from your workspace"
                    )
                await check_repository(
                    session,
                    workspace[0],
                    commit.repository,
                    self.settings.hosted_repository_limit,
                )
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
            if workspace is not None:
                count = await session.scalar(
                    select(func.count())
                    .select_from(SourceFile)
                    .where(SourceFile.snapshot_id == snapshot_id)
                )
                if count is not None and count > self.settings.ingestion_max_files:
                    raise IngestionError(
                        413,
                        "ingestion_limit",
                        "Repository exceeds the hosted file limit",
                    )
                await session.execute(
                    insert(WorkspaceSnapshot)
                    .values(workspace_id=workspace[0], snapshot_id=snapshot_id)
                    .on_conflict_do_nothing()
                )
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
        self,
        repository: str,
        ref: str | None,
        request_id: str,
        workspace: tuple[UUID, int] | None = None,
    ) -> SnapshotStatus:
        remaining = self.github_resume - monotonic()
        if workspace is not None and remaining > 0:
            raise IngestionError(
                503,
                "github_rate_limited",
                "GitHub rate limit reached",
                int(remaining) + 1,
            )
        if self.active >= self.settings.ingestion_concurrency:
            raise IngestionError(
                429, "ingestion_busy", "Ingestion capacity is full; retry later"
            )
        self.active += 1
        scheduled = False
        lease = None
        try:
            if workspace is not None and self.settings.deployment_mode == "hosted":
                lease = await reserve(
                    self.sessions, self.settings, workspace, repository
                )
            github = GitHub(self.client, self.settings)
            async with asyncio.timeout(self.settings.ingestion_timeout):
                commit = await github.resolve(repository, ref)
                snapshot_id, pending = await self.prepare(commit, workspace)
                if pending is not None or (
                    lease is not None and self.settings.hosted_prepare_indexes
                ):
                    task = asyncio.create_task(
                        self.run_submission(
                            github, commit, snapshot_id, pending, request_id, lease
                        )
                    )
                    self.tasks.add(task)
                    task.add_done_callback(self.release_task)
                    scheduled = True
                return await self.status(snapshot_id)
        except IngestionError as error:
            self.note_upstream(error)
            raise
        except TimeoutError:
            raise IngestionError(
                504, "ingestion_timeout", "Ingestion request timed out"
            ) from None
        finally:
            if not scheduled:
                self.active -= 1
                if lease is not None:
                    await release(self.sessions, lease)

    async def run_submission(
        self,
        github: GitHub,
        commit: Commit,
        snapshot_id: UUID,
        pending: datetime | None,
        request_id: str,
        lease: tuple[UUID, UUID] | None,
    ) -> None:
        try:
            if pending is not None:
                await self.run(github, commit, snapshot_id, pending, request_id)
            if lease is not None and self.settings.hosted_prepare_indexes:
                status = await self.status(snapshot_id)
                if status.state == IngestionState.COMPLETED:
                    from repobrain.graph.service import analyze_snapshot
                    from repobrain.search.service import build_index

                    try:
                        await analyze_snapshot(self.sessions, snapshot_id)
                        await build_index(self.sessions, snapshot_id)
                    except Exception as exc:
                        logger.warning(
                            "hosted_preparation_failed",
                            extra={
                                "event_fields": {
                                    "request_id": request_id,
                                    "reason": type(exc).__name__,
                                }
                            },
                        )
        finally:
            if lease is not None:
                await release(self.sessions, lease)

    def release_task(self, task: asyncio.Task[None]) -> None:
        # A task cancelled before its first step never enters run().
        self.tasks.discard(task)
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
            if isinstance(exc, IngestionError):
                self.note_upstream(exc)
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
