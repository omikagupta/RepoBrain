"""Persistent hosted usage windows and ingestion leases."""

import logging
from datetime import UTC, datetime, timedelta
from math import ceil
from uuid import UUID, uuid4

from sqlalchemy import Select, case, delete, func, or_, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from repobrain.database.models import (
    IngestionLease,
    Repository,
    RepositorySnapshot,
    UsageWindow,
    Workspace,
    WorkspaceSnapshot,
)
from repobrain.graph.exploration import ExplorationError
from repobrain.settings import Settings

logger = logging.getLogger("repobrain.quotas")


class QuotaExceeded(ExplorationError):
    def __init__(self, code: str, message: str, retry_after: int) -> None:
        super().__init__(429, code, message)
        self.retry_after = max(1, retry_after)


async def charge(
    session: AsyncSession, owner: UUID, kind: str, seconds: int, limit: int
) -> None:
    now = (await session.execute(select(func.statement_timestamp()))).scalar_one()
    start = datetime.fromtimestamp(int(now.timestamp()) // seconds * seconds, UTC)
    statement = insert(UsageWindow).values(
        owner_id=owner, kind=kind, window_start=start, count=1
    )
    changed = UsageWindow.window_start < start
    accepted = await session.scalar(
        statement.on_conflict_do_update(
            index_elements=[UsageWindow.owner_id, UsageWindow.kind],
            set_={
                "count": case((changed, 1), else_=UsageWindow.count + 1),
                "window_start": start,
            },
            where=or_(
                changed,
                (UsageWindow.window_start == start) & (UsageWindow.count < limit),
            ),
        ).returning(UsageWindow.count)
    )
    if accepted is None:
        raise QuotaExceeded(
            f"{kind}_limit",
            "Usage limit reached. Try again after the current window.",
            ceil((start + timedelta(seconds=seconds) - now).total_seconds()),
        )


def workspace_repositories(workspace_id: UUID) -> Select[tuple[str, str]]:
    return (
        select(Repository.owner, Repository.name)
        .join(RepositorySnapshot, RepositorySnapshot.repository_id == Repository.id)
        .join(WorkspaceSnapshot, WorkspaceSnapshot.snapshot_id == RepositorySnapshot.id)
        .where(WorkspaceSnapshot.workspace_id == workspace_id)
        .distinct()
    )


async def check_repository(
    session: AsyncSession, workspace: UUID, repository: str, limit: int
) -> None:
    rows = (
        await session.execute(workspace_repositories(workspace).limit(limit + 1))
    ).all()
    if len(rows) >= limit and not any(
        f"{row.owner}/{row.name}" == repository for row in rows
    ):
        raise QuotaExceeded(
            "repository_limit", "Remove a repository before adding another.", 60
        )


async def reserve(
    sessions: async_sessionmaker[AsyncSession],
    settings: Settings,
    workspace: tuple[UUID, int],
    repository: str,
) -> tuple[UUID, UUID]:
    async with sessions.begin() as session:
        # Serializes global occupancy checks across processes. Never held over I/O.
        await session.execute(text("SELECT pg_advisory_xact_lock(791279510126712043)"))
        row = await session.get(Workspace, workspace[0], with_for_update=True)
        if row is None or row.revision != workspace[1]:
            raise ExplorationError(
                409, "workspace_changed", "Retry from your workspace"
            )
        await check_repository(
            session, row.id, repository, settings.hosted_repository_limit
        )
        now = (await session.execute(select(func.statement_timestamp()))).scalar_one()
        await session.execute(
            delete(IngestionLease).where(IngestionLease.expires_at <= now)
        )
        leases = (
            await session.scalars(
                select(IngestionLease).order_by(IngestionLease.expires_at)
            )
        ).all()
        blocked = next(
            (lease for lease in leases if lease.owner_id == row.owner_id), None
        )
        if blocked is None and len(leases) >= settings.hosted_global_ingestions:
            blocked = leases[0]
        if blocked is not None:
            raise QuotaExceeded(
                "ingestion_busy",
                "An ingestion is already running.",
                min(15, ceil((blocked.expires_at - now).total_seconds())),
            )
        await charge(
            session, row.owner_id, "ingestion", 86400, settings.hosted_daily_ingestions
        )
        token = uuid4()
        lease_seconds = settings.ingestion_timeout * 2 + 120
        session.add(
            IngestionLease(
                owner_id=row.owner_id,
                token=token,
                expires_at=now + timedelta(seconds=lease_seconds),
            )
        )
        return row.owner_id, token


async def release(
    sessions: async_sessionmaker[AsyncSession], lease: tuple[UUID, UUID]
) -> None:
    try:
        async with sessions.begin() as session:
            await session.execute(
                delete(IngestionLease).where(
                    IngestionLease.owner_id == lease[0],
                    IngestionLease.token == lease[1],
                )
            )
    except Exception:
        logger.warning("ingestion_lease_release_failed")
