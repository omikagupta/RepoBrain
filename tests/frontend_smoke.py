"""Test-only backend and deterministic repository for the browser smoke workflow."""

import asyncio
import json
import os
from uuid import UUID

import uvicorn
from conftest import upgrade_fresh_database
from test_vector_retrieval import FakeProvider, seed

from repobrain.answers.models import GeneratorIdentity
from repobrain.answers.provider import Generated, GenerationInput
from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.graph.service import analyze_snapshot
from repobrain.main import create_app
from repobrain.search.service import build_index
from repobrain.search.vector import build_vector_index
from repobrain.settings import Settings

SNAPSHOT = UUID("9bdaf39e-b9e0-4acf-89a5-0bfcdda66f53")


class BrowserProvider:
    identity = GeneratorIdentity(provider="fixture", model="browser-demonstration")

    async def generate(self, request: GenerationInput) -> Generated:
        evidence = json.loads(request.evidence_json)["evidence"]
        citation = next(
            item["citation_id"] for item in evidence if item["path"] == "app.py"
        )
        return Generated(
            json.dumps(
                {
                    "status": "answered",
                    "claims": [
                        {
                            "kind": "observation",
                            "text": "The entry module imports read_file from reader.",
                            "citations": [citation],
                        }
                    ],
                    "limitations": ["Deterministic test demonstration."],
                }
            )
        )


async def prepare(settings: Settings) -> None:
    engine = create_database_engine(settings)
    try:
        async with engine.begin() as connection:
            await connection.run_sync(upgrade_fresh_database)
        sessions = create_session_factory(engine)
        snapshot = await seed(
            sessions,
            {
                "app.py": "from reader import read_file\n",
                "reader.py": "def read_file(path):\n    return path.read_text()\n",
            },
            snapshot_id=SNAPSHOT,
        )
        await analyze_snapshot(sessions, snapshot)
        await build_index(sessions, snapshot)
        await build_vector_index(sessions, snapshot, FakeProvider())
    finally:
        await engine.dispose()


if __name__ == "__main__":
    assert os.environ.get("REPOBRAIN_FRONTEND_SMOKE") == "1"
    settings = Settings()
    asyncio.run(prepare(settings))
    app = create_app(
        settings,
        embedding_provider=FakeProvider(),
        generation_provider=BrowserProvider(),
    )
    uvicorn.run(app, host="0.0.0.0", port=8000, access_log=False)
