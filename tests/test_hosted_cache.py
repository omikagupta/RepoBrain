import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import httpx
import pytest
from sqlalchemy import update
from test_tenancy import ISSUER

from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.database.models import (
    HostedCacheEntry,
    Repository,
    RepositorySnapshot,
    SaaSUser,
    Workspace,
    WorkspaceSnapshot,
)
from repobrain.ingestion.github import Commit
from repobrain.ingestion.service import IngestionService
from repobrain.quotas import QuotaExceeded
from repobrain.settings import Settings

pytestmark = pytest.mark.postgres


@pytest.mark.asyncio
async def test_cache_never_reclaims_legacy_or_granted_content(
    migrated_database: Settings,
) -> None:
    settings = Settings(
        database_url=migrated_database.database_url,
        deployment_mode="hosted",
        auth_issuer=ISSUER,
        hosted_cache_snapshots=1,
        hosted_cache_prune=True,
    )
    engine = create_database_engine(settings)
    sessions = create_session_factory(engine)
    async with httpx.AsyncClient() as client:
        service = IngestionService(sessions, client, settings)
        try:
            label = uuid4().hex
            async with sessions.begin() as session:
                owner = uuid4()
                session.add(SaaSUser(id=owner))
                await session.flush()
                workspace = Workspace(owner_id=owner)
                legacy = Repository(owner="cache-test", name=f"legacy-{label}")
                session.add_all([workspace, legacy])
                await session.flush()
                preserved = RepositorySnapshot(
                    repository_id=legacy.id, commit_sha="a" * 40
                )
                session.add(preserved)
                await session.flush()
                old_id, ws = preserved.id, workspace.id
            first, _ = await service.prepare(
                Commit(f"cache-test/one-{label}", "b" * 40, "c" * 40), (ws, 0)
            )
            async with sessions.begin() as session:
                await session.execute(
                    update(HostedCacheEntry)
                    .where(
                        HostedCacheEntry.snapshot_id == first,
                    )
                    .values(touched_at=datetime.now(UTC) - timedelta(days=8))
                )
            second = Commit(f"cache-test/two-{label}", "d" * 40, "e" * 40)
            with pytest.raises(QuotaExceeded) as err:
                await service.prepare(second, (ws, 0))
            assert err.value.code == "cache_capacity"
            async with sessions.begin() as session:
                grant = await session.get_one(WorkspaceSnapshot, (ws, first))
                await session.delete(grant)
            replacement, _ = await service.prepare(second, (ws, 0))
            async with sessions() as session:
                assert await session.get(RepositorySnapshot, first) is None
                assert await session.get(RepositorySnapshot, old_id) is not None
                assert await session.get(HostedCacheEntry, replacement) is not None
        finally:
            await engine.dispose()


@pytest.mark.asyncio
async def test_shutdown_during_indexing_allows_retry(
    migrated_database: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    from hashlib import sha256
    from uuid import UUID

    from repobrain.graph.service import analyze_snapshot
    from repobrain.ingestion.github import GitHub, PythonFile

    settings = Settings(
        database_url=migrated_database.database_url,
        deployment_mode="hosted",
        auth_issuer=ISSUER,
        hosted_prepare_indexes=True,
    )
    engine = create_database_engine(settings)
    sessions = create_session_factory(engine)
    owner = uuid4()
    token = owner
    started = asyncio.Event()
    calls = 0

    async def resolve(_self: GitHub, repo: str, _ref: str | None) -> Commit:
        return Commit(repo, "a" * 40, "b" * 40)

    async def collect(_self: GitHub, _commit: Commit) -> list[PythonFile]:
        nonlocal calls
        calls += 1
        source = "def restart():\n    return True\n"
        return [PythonFile("main.py", source, sha256(source.encode()).hexdigest(), 2)]

    async def stalled(_sessions: object, _snapshot: UUID) -> None:
        started.set()
        await asyncio.Event().wait()

    monkeypatch.setattr(GitHub, "resolve", resolve)
    monkeypatch.setattr(GitHub, "collect", collect)
    monkeypatch.setattr("repobrain.graph.service.analyze_snapshot", stalled)
    try:
        async with sessions.begin() as session:
            session.add(SaaSUser(id=token))
            await session.flush()
            row = Workspace(owner_id=token)
            session.add(row)
            await session.flush()
            workspace = (row.id, 0)
        async with httpx.AsyncClient() as client:
            repo = "cache-test/restart-" + uuid4().hex
            first = IngestionService(sessions, client, settings)
            result = await first.submit(repo, None, "first", workspace)
            await asyncio.wait_for(started.wait(), 5)
            await first.close()
            monkeypatch.setattr(
                "repobrain.graph.service.analyze_snapshot", analyze_snapshot
            )
            second = IngestionService(sessions, client, settings)
            retry = await second.submit(repo, None, "retry", workspace)
            assert retry.snapshot_id == result.snapshot_id
            await asyncio.wait_for(asyncio.gather(*tuple(second.tasks)), 45)
            async with sessions() as session:
                from repobrain.database.models import GraphAnalysis, SearchIndex

                assert await session.get(GraphAnalysis, retry.snapshot_id)
                assert await session.get(SearchIndex, retry.snapshot_id)
            assert calls == 1
    finally:
        await engine.dispose()
