import asyncio
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import update
from test_tenancy import ISSUER, Signing

from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.database.models import IngestionLease
from repobrain.graph.exploration import ExplorationError
from repobrain.ingestion.github import Commit, GitHub, IngestionError, PythonFile
from repobrain.main import create_app
from repobrain.quotas import QuotaExceeded, release, reserve
from repobrain.settings import Settings

pytestmark = pytest.mark.postgres


@pytest.mark.asyncio
async def test_hosted_quota_lifecycle(
    migrated_database: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    signer = Signing()
    settings = Settings(
        deployment_mode="hosted",
        auth_issuer=ISSUER,
        database_url=migrated_database.database_url,
        hosted_daily_ingestions=2,
        hosted_hourly_searches=1,
        hosted_repository_limit=1,
        hosted_prepare_indexes=True,
    )
    started, unblock = asyncio.Event(), asyncio.Event()
    name = f"owner/sample-{uuid4().hex}"
    attempts = 0
    jobs = 0

    async def resolve(_self: GitHub, repo: str, _ref: str | None) -> Commit:
        nonlocal attempts
        attempts += 1
        return Commit(repo, "b" * 40, "c" * 40)

    async def collect(_self: GitHub, _commit: Commit) -> list[PythonFile]:
        from hashlib import sha256

        nonlocal jobs
        jobs += 1
        if jobs == 1:
            started.set()
            await unblock.wait()
        content = "def quota_probe():\n    return 1\n"
        return [PythonFile("main.py", content, sha256(content.encode()).hexdigest(), 2)]

    monkeypatch.setattr(GitHub, "resolve", resolve)
    monkeypatch.setattr(GitHub, "collect", collect)
    headers = signer.headers(uuid4())
    app = create_app(settings, auth_transport=httpx.MockTransport(signer.jwks))
    ingest, workspace = "/api/v1/repositories/ingestions", "/api/v1/workspace"
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers=headers,
        ) as client,
    ):
        ws_id = UUID((await client.post(workspace)).json()["id"])
        first = await client.post(ingest, json={"repository": name})
        assert first.status_code == 202
        await asyncio.wait_for(started.wait(), 5)
        duplicate = await client.post(ingest, json={"repository": name})
        assert (
            duplicate.status_code == 429 and int(duplicate.headers["Retry-After"]) > 0
        )
        assert attempts == 1

        # A separate service instance cannot take the same active lease.
        engine = create_database_engine(settings)
        sessions = create_session_factory(engine)
        try:
            with pytest.raises(QuotaExceeded) as err:
                await reserve(sessions, settings, (ws_id, 0), name)
            assert err.value.code == "ingestion_busy"
        finally:
            await engine.dispose()

        # Cancel the admitted collection. Its usage remains consumed.
        await app.state.ingestion.close()
        snapshot = first.json()["snapshot_id"]
        assert (await client.get(f"/api/v1/ingestions/{snapshot}")).json()[
            "state"
        ] == "failed"
        second = await client.post(ingest, json={"repository": name})
        assert second.status_code == 202 and second.json()["snapshot_id"] == snapshot
        await asyncio.wait_for(asyncio.gather(*tuple(app.state.ingestion.tasks)), 45)
        assert jobs == 2
        scope = f"/api/v1/snapshots/{snapshot}"
        ready = await client.get(scope + "/readiness")
        assert ready.json()["graph_analyzed"] and ready.json()["lexical_version"]
        assert ready.json()["vector_version"] is None
        assert (await client.get(workspace)).json()["repository_count"] == 1
        over = await client.post(ingest, json={"repository": "owner/other"})
        assert (
            over.status_code == 429
            and over.json()["error"]["code"] == "repository_limit"
        )
        query = scope + "/search/lexical?q=quota_probe"
        responses = await asyncio.gather(client.get(query), client.get(query))
        assert sorted(r.status_code for r in responses) == [200, 429]
        assert all(
            r.headers.get("Retry-After") for r in responses if r.status_code == 429
        )

    restarted = create_app(settings, auth_transport=httpx.MockTransport(signer.jwks))
    async with (
        restarted.router.lifespan_context(restarted),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=restarted),
            base_url="http://test",
            headers=headers,
        ) as client,
    ):
        assert (await client.get(query)).status_code == 429
        third = await client.post(ingest, json={"repository": name})
        assert third.status_code == 429
        assert third.json()["error"]["code"] == "ingestion_limit"
        assert attempts == 2


@pytest.mark.asyncio
async def test_expiration_and_upstream_failure(
    migrated_database: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr("repobrain.hosted_bounds.monotonic", lambda: 123.0)
    signer = Signing()
    settings = Settings(
        deployment_mode="hosted",
        auth_issuer=ISSUER,
        database_url=migrated_database.database_url,
        hosted_public_per_minute=12,
    )
    calls = 0

    async def resolve(_self: GitHub, _repo: str, _ref: str | None) -> Commit:
        nonlocal calls
        calls += 1
        raise IngestionError(503, "github_rate_limited", "Retry later", 45)

    monkeypatch.setattr(GitHub, "resolve", resolve)
    app = create_app(settings, auth_transport=httpx.MockTransport(signer.jwks))
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
            headers=signer.headers(uuid4()),
        ) as client,
    ):
        path = "/api/v1/repositories/ingestions"
        workspace = UUID((await client.post("/api/v1/workspace")).json()["id"])
        engine = create_database_engine(settings)
        sessions = create_session_factory(engine)
        try:
            old = await reserve(sessions, settings, (workspace, 0), "owner/repo")
            async with sessions.begin() as session:
                await session.execute(
                    update(IngestionLease)
                    .where(
                        IngestionLease.token == old[1],
                    )
                    .values(expires_at=datetime.now(UTC) - timedelta(seconds=1))
                )
            replacement = await reserve(
                sessions, settings, (workspace, 0), "owner/repo"
            )
            await release(sessions, old)
            with pytest.raises(ExplorationError):
                await reserve(sessions, settings, (workspace, 0), "owner/repo")
            await release(sessions, replacement)
        finally:
            await engine.dispose()
        oversized = await client.post(
            path, json={"repository": "owner/repo", "extra": "x" * 9000}
        )
        assert oversized.status_code == 413
        for _ in range(2):
            upstream = await client.post(path, json={"repository": "owner/repo"})
            assert upstream.status_code == 503
            assert 0 < int(upstream.headers["Retry-After"]) <= 46
        assert calls == 1
        for _ in range(12):
            result = await client.get("/healthz")
            assert result.status_code == 200
        denied = await client.get("/healthz")
        assert denied.status_code == 429 and denied.headers["Retry-After"]
