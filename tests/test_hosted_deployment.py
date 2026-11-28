from pathlib import Path

import httpx
import pytest
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker
from test_tenancy import ISSUER

from repobrain.hosted import deployed_app
from repobrain.main import create_app, verify_database
from repobrain.settings import Settings


def test_hosted_entrypoint_refuses_local(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("REPOBRAIN_DEPLOYMENT_MODE", "local")
    with pytest.raises(
        RuntimeError, match="Hosted deployment configuration is invalid"
    ):
        deployed_app()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_ready_and_cors_against_migrated_database(
    migrated_database: Settings,
) -> None:
    origin = "https://ui.example.invalid"
    settings = Settings(
        deployment_mode="hosted",
        auth_issuer=ISSUER,
        hosted_frontend_origin=origin,
        database_url=migrated_database.database_url,
    )
    app = create_app(settings)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://test",
        ) as client,
    ):
        assert (await client.get("/readyz")).json() == {"status": "ready"}
        for candidate in (origin, origin + ".evil.invalid"):
            response = await client.options(
                "/api/v1/workspace",
                headers={
                    "Origin": candidate,
                    "Access-Control-Request-Method": "GET",
                    "Access-Control-Request-Headers": "Authorization",
                },
            )
            if candidate == origin:
                assert response.status_code == 200
                assert response.headers["Access-Control-Allow-Origin"] == origin
            else:
                assert response.status_code == 400
                assert "Access-Control-Allow-Origin" not in response.headers
        missing = await client.get("/api/v1/workspace", headers={"Origin": origin})
        assert missing.status_code == 401
        assert missing.headers["Access-Control-Allow-Origin"] == origin


@pytest.mark.asyncio
async def test_deployment_readiness_fails_closed_without_schema() -> None:
    sessions: async_sessionmaker[AsyncSession] = async_sessionmaker()
    with pytest.raises(RuntimeError, match="incompatible schema"):
        await verify_database(sessions)
