import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from test_ingestion import SHA, FixtureGitHub
from test_tenancy import ISSUER, Signing

from repobrain.main import create_app
from repobrain.settings import Settings


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_two_user_hosted_staging(migrated_database: Settings) -> None:
    settings = Settings(
        deployment_mode="hosted",
        auth_issuer=ISSUER,
        database_url=migrated_database.database_url,
        hosted_hourly_searches=1,
        hosted_prepare_indexes=True,
    )
    github = FixtureGitHub("sample/staging-" + uuid4().hex)
    signer = Signing()
    alice, bob = uuid4(), uuid4()
    a, b = signer.headers(alice), signer.headers(bob)
    app = create_app(
        settings,
        github_transport=github.transport(),
        auth_transport=httpx.MockTransport(signer.jwks),
    )
    workspace = "/api/v1/workspace"
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://local",
        ) as client,
    ):
        assert (await client.get("/readyz")).status_code == 200
        expired = signer.token(alice, exp=int(datetime.now(UTC).timestamp()) - 1)
        assert (
            await client.get(workspace, headers={"Authorization": "Bearer " + expired})
        ).status_code == 401
        for headers in (a, b):
            assert (await client.post(workspace, headers=headers)).status_code == 200
        submitted = await client.post(
            "/api/v1/repositories/ingestions",
            headers=a,
            json={"repository": github.repository},
        )
        assert submitted.status_code == 202
        snapshot = submitted.json()["snapshot_id"]
        assert submitted.json()["commit_sha"] == SHA
        await asyncio.wait_for(asyncio.gather(*tuple(app.state.ingestion.tasks)), 45)
        scope = f"/api/v1/snapshots/{snapshot}"
        ready = (await client.get(scope + "/readiness", headers=a)).json()
        assert ready["graph_analyzed"] and ready["lexical_version"]
        source = scope + "/source"
        search = scope + "/search/lexical"
        paths: list[tuple[str, dict[str, str]]] = [
            (scope + "/graph", {}),
            (scope + "/nodes", {}),
            (source, {"path": str(github.entries[0]["path"])}),
            (search, {"q": "return"}),
        ]
        for path, params in paths:
            visible = await client.get(path, headers=a, params=params)
            assert visible.status_code == 200, visible.text
            assert (await client.get(path, headers=b, params=params)).status_code == 404
        quota = await client.get(search, headers=a, params={"q": "return"})
        assert quota.status_code == 429 and quota.headers["Retry-After"]
        repositories = (await client.get(workspace, headers=a)).json()["snapshots"]
        remove = workspace + "/repositories/" + repositories[0]["id"]
        assert (await client.delete(remove, headers=b)).status_code == 404
        assert (
            await client.delete(workspace + "/account", headers=a)
        ).status_code == 204
        assert (await client.get(scope + "/graph", headers=a)).status_code == 404
        assert (await client.post(workspace, headers=a)).status_code == 404
        assert (await client.get(workspace, headers=b)).json()["snapshots"] == []
