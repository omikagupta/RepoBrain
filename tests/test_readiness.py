from uuid import uuid4

import httpx
import pytest
from test_vector_retrieval import FakeProvider, seed

from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.graph.service import analyze_snapshot
from repobrain.main import create_app
from repobrain.search.chunking import VERSION
from repobrain.search.service import build_index
from repobrain.search.vector import VECTOR_VERSION, build_vector_index
from repobrain.settings import Settings


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_readiness_reports_only_requested_snapshot(
    migrated_database: Settings,
) -> None:
    engine = create_database_engine(migrated_database)
    sessions = create_session_factory(engine)
    provider = FakeProvider()
    app = create_app(migrated_database, embedding_provider=provider)
    try:
        ready = await seed(sessions, {"file.py": "pass\n"})
        pending = await seed(sessions, {})
        await analyze_snapshot(sessions, ready)
        await build_index(sessions, ready)
        await build_vector_index(sessions, ready, provider)
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://test"
            ) as client,
        ):
            root = "/api/v1/snapshots"
            response = await client.get(f"{root}/{ready}/readiness")
            assert response.status_code == 200
            assert response.json()["snapshot_id"] == str(ready)
            assert response.json()["graph_analyzed"] is True
            assert response.json()["lexical_version"] == VERSION
            assert response.json()["vector_version"] == VECTOR_VERSION
            response = await client.get(f"{root}/{pending}/readiness")
            assert response.status_code == 200
            assert response.json()["graph_analyzed"] is False
            assert response.json()["lexical_version"] is None
            assert response.json()["vector_version"] is None
            missing = await client.get(f"{root}/{uuid4()}/readiness")
            assert missing.status_code == 404
            assert (
                missing.json()["error"]["request_id"] == missing.headers["x-request-id"]
            )
    finally:
        await engine.dispose()
