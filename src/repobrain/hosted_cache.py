"""Storage admission for snapshots created by hosted ingestion."""

from datetime import timedelta
from uuid import UUID

from sqlalchemy import delete, exists, func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from repobrain.database.models import (
    HostedCacheEntry,
    RepositorySnapshot,
    WorkspaceSnapshot,
)
from repobrain.quotas import QuotaExceeded
from repobrain.settings import Settings


async def lock_cache(session: AsyncSession) -> None:
    await session.execute(text("SELECT pg_advisory_xact_lock(791279510126712044)"))


async def claim_cache(
    session: AsyncSession, settings: Settings, snapshot_id: UUID, created: bool
) -> None:
    now = (await session.execute(select(func.statement_timestamp()))).scalar_one()
    entry = await session.get(HostedCacheEntry, snapshot_id)
    if entry is not None:
        entry.touched_at = now
        return
    if not created:
        # Legacy and operator-owned snapshots never enter the prunable set.
        return
    if settings.hosted_cache_prune:
        old = (
            select(HostedCacheEntry.snapshot_id)
            .where(
                HostedCacheEntry.touched_at
                < now - timedelta(hours=settings.hosted_cache_retention_hours),
                ~exists().where(
                    WorkspaceSnapshot.snapshot_id == HostedCacheEntry.snapshot_id
                ),
            )
            .order_by(HostedCacheEntry.touched_at, HostedCacheEntry.snapshot_id)
            .limit(10)
        )
        await session.execute(
            delete(RepositorySnapshot).where(RepositorySnapshot.id.in_(old))
        )
    usage = (
        await session.execute(
            select(
                func.count(HostedCacheEntry.snapshot_id),
                func.coalesce(func.sum(HostedCacheEntry.reserved_bytes), 0),
            )
        )
    ).one()
    size = settings.ingestion_max_total_bytes
    if (
        usage[0] >= settings.hosted_cache_snapshots
        or usage[1] + size > settings.hosted_cache_bytes
    ):
        raise QuotaExceeded(
            "cache_capacity", "Hosted snapshot storage is at capacity.", 3600
        )
    session.add(
        HostedCacheEntry(snapshot_id=snapshot_id, reserved_bytes=size, touched_at=now)
    )
