import asyncio
from datetime import UTC, datetime, timedelta
from hashlib import sha1, sha256
from typing import Any
from uuid import UUID, uuid4

import httpx
import pytest
from sqlalchemy import select

from repobrain.database.connection import create_database_engine, create_session_factory
from repobrain.database.models import (
    IngestionState,
    Repository,
    RepositorySnapshot,
    SourceFile,
)
from repobrain.ingestion.github import GitHub, IngestionError
from repobrain.main import create_app
from repobrain.settings import Settings

SHA = "a" * 40
TREE = "b" * 40
SOURCE = b"first\r\nlast"
BLOB = sha1(b"blob 11\0" + SOURCE, usedforsecurity=False).hexdigest()
POST = "/api/v1/repositories/ingestions"


def entry(path: str = "src/main.py", **overrides: object) -> dict[str, object]:
    return {
        "path": path,
        "type": "blob",
        "mode": "100644",
        "size": len(SOURCE),
        "sha": BLOB,
        **overrides,
    }


class FixtureGitHub:
    def __init__(self, repository: str = "sample/project") -> None:
        self.repository = repository
        self.entries = [entry()]
        self.contents = {BLOB: SOURCE}
        self.private = False
        self.missing = False
        self.paths: list[str] = []
        self.pause: asyncio.Event | None = None
        self.entered = asyncio.Event()

    async def handle(self, request: httpx.Request) -> httpx.Response:
        assert request.url.scheme == "https"
        assert request.url.host == "api.github.com"
        assert "authorization" not in request.headers
        path = request.url.path
        self.paths.append(path)
        root = f"/repos/{self.repository}"
        if path == root:
            if self.missing:
                return httpx.Response(404)
            return httpx.Response(
                200,
                json={
                    "private": self.private,
                    "visibility": "private" if self.private else "public",
                    "full_name": self.repository.upper(),
                    "default_branch": "trunk",
                },
            )
        if path in {f"{root}/commits/{ref}" for ref in ("refs/heads/trunk", "v1", SHA)}:
            return httpx.Response(
                200, json={"sha": SHA, "commit": {"tree": {"sha": TREE}}}
            )
        if path.startswith(f"{root}/commits/"):
            return httpx.Response(404)
        if path == f"{root}/git/trees/{TREE}":
            assert request.url.params["recursive"] == "1"
            return httpx.Response(200, json={"truncated": False, "tree": self.entries})
        if path.startswith(f"{root}/git/blobs/"):
            self.entered.set()
            if self.pause is not None:
                await self.pause.wait()
            return httpx.Response(200, content=self.contents[path.rsplit("/", 1)[1]])
        raise AssertionError("Unexpected GitHub endpoint")

    def transport(self) -> httpx.MockTransport:
        return httpx.MockTransport(self.handle)


@pytest.mark.asyncio
@pytest.mark.parametrize("ref", [None, "v1", SHA])
async def test_pinned_resolution_and_filtering(ref: str | None) -> None:
    github = FixtureGitHub()
    binary = sha1(b"blob 2\0a\x00", usedforsecurity=False).hexdigest()
    github.contents[binary] = b"a\x00"
    github.entries.extend(
        [
            entry("link.py", mode="120000"),
            entry("module.py", mode="160000", type="commit"),
            entry("vendor/library.py"),
            entry("generated/auto.py"),
            entry("large.py", size=999999),
            entry("binary.py", sha=binary, size=2),
            entry("README.md"),
        ]
    )
    async with httpx.AsyncClient(transport=github.transport()) as http:
        client = GitHub(http, Settings(ingestion_max_file_bytes=32))
        commit = await client.resolve(github.repository, ref)
        files = await client.collect(commit)
    assert commit.sha == SHA and commit.repository == github.repository
    assert github.paths[1].endswith(f"/commits/{ref or 'refs/heads/trunk'}")
    assert [file.path for file in files] == ["src/main.py"]
    assert files[0].line_count == 2
    assert files[0].content == SOURCE.decode()
    assert files[0].content_sha256 == sha256(SOURCE).hexdigest()


@pytest.mark.asyncio
@pytest.mark.parametrize("kind", ["private", "missing", "invalid_ref", "redirect"])
async def test_safe_upstream_failures(kind: str) -> None:
    github = FixtureGitHub()
    github.private = kind == "private"
    github.missing = kind == "missing"
    transport = github.transport()
    if kind == "redirect":
        transport = httpx.MockTransport(
            lambda _: httpx.Response(302, headers={"Location": "http://127.0.0.1/"})
        )
    expected = {"private": 404, "missing": 404, "invalid_ref": 422, "redirect": 502}
    async with httpx.AsyncClient(transport=transport, follow_redirects=True) as http:
        with pytest.raises(IngestionError) as error:
            await GitHub(http, Settings()).resolve(github.repository, "absent")
    assert error.value.status == expected[kind]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "path", ["../bad.py", "/bad.py", "C:/bad.py", "src\\bad.py", "src/main.py"]
)
async def test_rejects_traversal_and_duplicate_paths(path: str) -> None:
    github = FixtureGitHub()
    github.entries.append(entry(path))
    async with httpx.AsyncClient(transport=github.transport()) as http:
        client = GitHub(http, Settings())
        commit = await client.resolve(github.repository, None)
        with pytest.raises(IngestionError):
            await client.collect(commit)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "setting",
    ["ingestion_max_files", "ingestion_max_total_bytes", "ingestion_max_network_bytes"],
)
async def test_ingestion_limits(setting: str) -> None:
    github = FixtureGitHub()
    github.entries.append(entry("second.py"))
    settings = Settings.model_validate({setting: 1})
    async with httpx.AsyncClient(transport=github.transport()) as http:
        client = GitHub(http, settings)
        with pytest.raises(IngestionError) as error:
            commit = await client.resolve(github.repository, None)
            await client.collect(commit)
    assert error.value.status == 413


@pytest.mark.asyncio
async def test_stream_budget_without_content_length() -> None:
    class Chunks(httpx.AsyncByteStream):
        async def __aiter__(self) -> Any:
            yield b"x" * 16384
            yield b"y" * 16384
            pytest.fail("Read past the ingress limit")

    transport = httpx.MockTransport(lambda _: httpx.Response(200, stream=Chunks()))
    async with httpx.AsyncClient(transport=transport) as http:
        with pytest.raises(IngestionError) as error:
            await GitHub(http, Settings(ingestion_max_network_bytes=20000)).resolve(
                "sample/project", None
            )
    assert error.value.status == 413


@pytest.mark.asyncio
async def test_api_rejects_unsafe_inputs_without_database() -> None:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=create_app()), base_url="http://test"
    ) as api:
        for body in [
            {"repository": "https://github.com/sample/project"},
            {"repository": "bad--owner/project"},
            {"repository": "sample/.."},
            {"repository": "sample/project", "ref": "heads/../other"},
        ]:
            response = await api.post(
                POST, json=body, headers={"X-Request-ID": "invalid-input"}
            )
            assert response.status_code == 422
            assert response.json()["error"]["request_id"] == "invalid-input"


async def poll(api: httpx.AsyncClient, location: str, state: str) -> dict[str, Any]:
    async with asyncio.timeout(5):
        while True:
            response = await api.get(location)
            assert response.status_code == 200, response.text
            data: dict[str, Any] = response.json()
            if data["state"] == state:
                return data
            await asyncio.sleep(0.02)


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_api_ingestion_concurrent_dedup_and_persistence(
    migrated_database: Settings,
) -> None:
    github = FixtureGitHub(f"sample/repo-{uuid4().hex}")
    github.pause = asyncio.Event()
    settings = migrated_database.model_copy(update={"ingestion_concurrency": 2})
    app = create_app(settings, github_transport=github.transport())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as api,
    ):
        body = {"repository": github.repository.upper()}
        first, duplicate = await asyncio.gather(
            api.post(POST, json=body), api.post(POST, json=body)
        )
        assert first.status_code == duplicate.status_code == 202, (
            first.text,
            duplicate.text,
        )
        location = first.headers["location"]
        assert location == duplicate.headers["location"]
        await poll(api, location, "running")
        github.pause.set()
        completed = await poll(api, location, "completed")
        assert completed["repository"] == github.repository
        assert completed["commit_sha"] == SHA and completed["file_count"] == 1
        assert (await api.post(POST, json=body)).status_code == 200
        assert sum("/blobs/" in path for path in github.paths) == 1
    engine = create_database_engine(settings)
    try:
        async with create_session_factory(engine)() as session:
            rows = (
                await session.scalars(
                    select(SourceFile).where(
                        SourceFile.snapshot_id == UUID(completed["snapshot_id"])
                    )
                )
            ).all()
            assert len(rows) == 1
            assert rows[0].path == "src/main.py"
            assert rows[0].content == SOURCE.decode()
            assert rows[0].content_sha256 == sha256(SOURCE).hexdigest()
            assert rows[0].line_count == 2
    finally:
        await engine.dispose()


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_interrupted_ingestion_is_retryable(migrated_database: Settings) -> None:
    github = FixtureGitHub(f"sample/repo-{uuid4().hex}")
    github.pause = asyncio.Event()
    app = create_app(migrated_database, github_transport=github.transport())
    body = {"repository": github.repository}
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as api,
    ):
        response = await api.post(POST, json=body)
        assert response.status_code == 202, response.text
        location = response.headers["location"]
        async with asyncio.timeout(5):
            await github.entered.wait()
        busy = await api.post(POST, json=body)
        assert busy.status_code == 429
    github.pause = None
    app = create_app(migrated_database, github_transport=github.transport())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as api,
    ):
        failed = await poll(api, location, "failed")
        assert failed["file_count"] == 0
        assert failed["error"]["code"] == "ingestion_failed"
        retry = await api.post(POST, json=body)
        assert retry.status_code == 202 and retry.headers["location"] == location
        assert (await poll(api, location, "completed"))["file_count"] == 1


@pytest.mark.postgres
@pytest.mark.asyncio
async def test_abandoned_snapshot_is_recovered(migrated_database: Settings) -> None:
    name = f"repo-{uuid4().hex}"
    github = FixtureGitHub(f"sample/{name}")
    engine = create_database_engine(migrated_database)
    try:
        async with create_session_factory(engine).begin() as session:
            repository = Repository(owner="sample", name=name)
            session.add(repository)
            await session.flush()
            snapshot = RepositorySnapshot(
                repository_id=repository.id,
                commit_sha=SHA,
                ingestion_state=IngestionState.RUNNING,
                updated_at=datetime.now(UTC) - timedelta(minutes=10),
            )
            session.add(snapshot)
            await session.flush()
            location = f"/api/v1/ingestions/{snapshot.id}"
    finally:
        await engine.dispose()

    app = create_app(migrated_database, github_transport=github.transport())
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as api,
    ):
        assert (await poll(api, location, "failed"))["file_count"] == 0
        retry = await api.post(POST, json={"repository": github.repository, "ref": SHA})
        assert retry.status_code == 202 and retry.headers["location"] == location
        assert (await poll(api, location, "completed"))["commit_sha"] == SHA
