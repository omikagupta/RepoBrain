import asyncio
import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec
from sqlalchemy import select

from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.database.models import IngestionState, Repository, RepositorySnapshot
from repobrain.graph.exploration import ExplorationError
from repobrain.ingestion.github import Commit, GitHub
from repobrain.main import create_app
from repobrain.settings import Settings
from repobrain.tenancy import Tokens

ISSUER = "https://identity.example.invalid/auth/v1"


class Signing:
    def __init__(self) -> None:
        self.private = ec.generate_private_key(ec.SECP256R1())
        self.kid = "test-key"

    def jwks(self, request: httpx.Request) -> httpx.Response:
        assert str(request.url) == ISSUER + "/.well-known/jwks.json"
        key = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(self.private.public_key()))
        return httpx.Response(
            200, json={"keys": [dict(key, kid=self.kid, alg="ES256")]}
        )

    def token(self, subject: UUID, **overrides: object) -> str:
        claims = {
            "iss": ISSUER,
            "aud": "authenticated",
            "sub": str(subject),
            "role": "authenticated",
            "exp": int((datetime.now(UTC) + timedelta(minutes=2)).timestamp()),
            **overrides,
        }
        return jwt.encode(claims, self.private, "ES256", headers={"kid": self.kid})

    def headers(self, subject: UUID) -> dict[str, str]:
        return {"Authorization": "Bearer " + self.token(subject)}


@pytest.mark.asyncio
async def test_signature_claims_and_rotation() -> None:
    signer = Signing()
    checker = Tokens(ISSUER, "authenticated", httpx.MockTransport(signer.jwks))
    subject = uuid4()
    assert await checker.subject(signer.token(subject)) == subject
    wrong = Signing()
    for token in (
        "malformed",
        jwt.encode({"sub": str(subject)}, key="", algorithm="none"),
        wrong.token(subject),
        signer.token(subject, iss="https://wrong.invalid/auth/v1"),
        signer.token(subject, aud="wrong"),
        signer.token(subject, exp=1),
        signer.token(subject, sub="not-a-uuid"),
        signer.token(subject, role="anon"),
    ):
        with pytest.raises(ExplorationError) as error:
            await checker.subject(token)
        assert error.value.status == 401
    signer.kid = "rotated"
    signer.private = ec.generate_private_key(ec.SECP256R1())
    checker.next_refresh = 0
    assert await checker.subject(signer.token(subject)) == subject
    assert "test-key" not in checker.keys


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_hosted_ownership_and_ingestion_race(
    migrated_database: Settings, monkeypatch: pytest.MonkeyPatch
) -> None:
    signer = Signing()
    settings = Settings(
        deployment_mode="hosted",
        auth_issuer=ISSUER,
        database_url=migrated_database.database_url,
    )
    app = create_app(settings, auth_transport=httpx.MockTransport(signer.jwks))
    assert app.state.embedding_provider is None
    alice, bob = signer.headers(uuid4()), signer.headers(uuid4())
    engine = create_database_engine(settings)
    sessions = create_session_factory(engine)
    repository = f"owner/r-{uuid4().hex}"
    started, proceed = asyncio.Event(), asyncio.Event()

    async def resolve(_self: GitHub, name: str, _ref: str | None) -> Commit:
        started.set()
        await proceed.wait()
        return Commit(name, "a" * 40, "b" * 40)

    monkeypatch.setattr(GitHub, "resolve", resolve)
    try:
        async with sessions.begin() as session:
            row = Repository(owner="owner", name=repository.split("/")[1])
            session.add(row)
            await session.flush()
            snap = RepositorySnapshot(
                repository_id=row.id,
                commit_sha="a" * 40,
                ingestion_state=IngestionState.COMPLETED,
            )
            session.add(snap)
            await session.flush()
            snapshot, repository_id = snap.id, row.id
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app),
                base_url="http://test",
            ) as client,
        ):
            assert (await client.get("/healthz")).status_code == 200
            workspace = "/api/v1/workspace"
            ingest = "/api/v1/repositories/ingestions"
            assert (
                await client.post(ingest, json={"repository": repository})
            ).status_code == 401
            assert (
                await client.post(ingest, json={"repository": repository}, headers=bob)
            ).status_code == 404
            first, second = await asyncio.gather(
                *(client.post(workspace, headers=alice) for _ in range(2))
            )
            assert first.status_code == second.status_code == 200
            assert first.json()["id"] == second.json()["id"]
            assert (await client.post(workspace, headers=bob)).status_code == 200
            source = f"/api/v1/snapshots/{snapshot}"
            polling = f"/api/v1/ingestions/{snapshot}"
            assert (await client.get(polling, headers=alice)).status_code == 404
            proceed.set()
            assert (
                await client.post(
                    ingest, json={"repository": repository}, headers=alice
                )
            ).status_code == 200

            for suffix in (
                "/readiness",
                "/graph",
                "/nodes",
                "/edges",
                f"/neighborhood?node_id={uuid4()}",
                "/source?path=file.py",
                "/search/lexical?q=code",
                "/search/vector?q=code",
                "/search/hybrid?q=code",
                "/search/graph-enhanced?q=code",
            ):
                assert (await client.get(source + suffix)).status_code == 401
                assert (
                    await client.get(source + suffix, headers=bob)
                ).status_code == 404
            payload = {"question": "How is code parsed?", "retrieval_mode": "lexical"}
            assert (
                await client.post(source + "/answer", json=payload)
            ).status_code == 401
            assert (
                await client.post(source + "/answer", headers=bob, json=payload)
            ).status_code == 404
            assert (
                await client.post(source + "/answer", headers=alice, json=payload)
            ).status_code == 503
            assert (
                await client.get(source + "/readiness", headers=alice)
            ).status_code == 200
            assert (
                await client.get(source + "/search/vector?q=code", headers=alice)
            ).status_code == 503
            assert (await client.get(polling, headers=bob)).status_code == 404

            remove = f"{workspace}/repositories/{repository_id}"
            assert (await client.delete(remove, headers=bob)).status_code == 404
            assert (await client.delete(remove)).status_code == 401
            assert (
                await client.post(ingest, json={"repository": repository}, headers=bob)
            ).status_code == 200
            started.clear()
            proceed.clear()
            async with asyncio.timeout(10):
                task = asyncio.create_task(
                    client.post(ingest, json={"repository": repository}, headers=alice)
                )
                try:
                    await started.wait()
                    assert (
                        await client.delete(remove, headers=alice)
                    ).status_code == 204
                finally:
                    proceed.set()
                assert (await task).status_code == 409
            assert (await client.get(polling, headers=alice)).status_code == 404
            assert (await client.get(polling, headers=bob)).status_code == 200
            assert (await client.delete(workspace, headers=bob)).status_code == 204
            assert (await client.get(polling, headers=bob)).status_code == 404
            assert (
                await client.delete(workspace + "/account", headers=alice)
            ).status_code == 204
            assert (await client.post(workspace, headers=alice)).status_code == 404
        async with sessions() as session:
            assert (
                await session.scalar(
                    select(RepositorySnapshot.id).where(
                        RepositorySnapshot.id == snapshot,
                    )
                )
                == snapshot
            )
    finally:
        await engine.dispose()
