"""Offline capped runtime probe with real project source streamed via fake GitHub."""

import asyncio
import json
import sys
from hashlib import sha1
from pathlib import Path
from time import monotonic
from uuid import uuid4

import httpx
import jwt
from cryptography.hazmat.primitives.asymmetric import ec

START = monotonic()

from repobrain.main import create_app  # noqa: E402
from repobrain.settings import Settings  # noqa: E402


async def main() -> None:
    root = Path("/sample")
    project = "sample/" + uuid4().hex
    files = sorted(root.rglob("*.py"))
    blobs = {}
    tree = []
    for path in files:
        data = path.read_bytes()
        sha = sha1(
            f"blob {len(data)}\0".encode() + data, usedforsecurity=False
        ).hexdigest()
        blobs[sha] = data
        tree.append(
            {
                "path": path.relative_to(root).as_posix(),
                "type": "blob",
                "mode": "100644",
                "sha": sha,
                "size": len(data),
            }
        )

    def github(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if "/commits/" in path:
            return httpx.Response(
                200, json={"sha": "a" * 40, "commit": {"tree": {"sha": "b" * 40}}}
            )
        if "/trees/" in path:
            return httpx.Response(
                200, json={"sha": "b" * 40, "truncated": False, "tree": tree}
            )
        if "/blobs/" in path:
            return httpx.Response(200, content=blobs[path.split("/")[-1]])
        return httpx.Response(
            200,
            json={
                "full_name": project,
                "private": False,
                "visibility": "public",
                "default_branch": "main",
            },
        )

    settings = Settings()
    private = ec.generate_private_key(ec.SECP256R1())
    key = json.loads(jwt.algorithms.ECAlgorithm.to_jwk(private.public_key()))
    jwks = httpx.MockTransport(
        lambda _: httpx.Response(
            200, json={"keys": [dict(key, kid="probe", alg="ES256")]}
        )
    )
    app = create_app(
        settings, auth_transport=jwks, github_transport=httpx.MockTransport(github)
    )
    token = jwt.encode(
        {
            "iss": settings.auth_issuer,
            "aud": "authenticated",
            "role": "authenticated",
            "sub": str(uuid4()),
            "exp": 4102444800,
        },
        private,
        "ES256",
        headers={"kid": "probe"},
    )
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://local",
            headers={"Authorization": "Bearer " + token},
        ) as client,
    ):
        assert (await client.get("/healthz")).status_code == 200
        startup = monotonic() - START
        provisioned = await client.post("/api/v1/workspace")
        assert provisioned.is_success, provisioned.text
        start = monotonic()
        response = await client.post(
            "/api/v1/repositories/ingestions", json={"repository": project}
        )
        assert response.is_success, response.text
        snapshot = response.json()["snapshot_id"]
        await asyncio.wait_for(asyncio.gather(*tuple(app.state.ingestion.tasks)), 115)
        wall = monotonic() - start
        ready = await client.get(f"/api/v1/snapshots/{snapshot}/readiness")
        status = await client.get(f"/api/v1/ingestions/{snapshot}")
        graph = await client.get(f"/api/v1/snapshots/{snapshot}/graph")
        search = await client.get(
            f"/api/v1/snapshots/{snapshot}/search/lexical?q=repository"
        )
        cgroup = Path("/sys/fs/cgroup")
        assert "onnxruntime" not in sys.modules
        print(
            json.dumps(
                {
                    "startup_seconds": round(startup, 3),
                    "workload_seconds": round(wall, 3),
                    "files": len(tree),
                    "source_bytes": sum(item["size"] for item in tree),
                    "ingestion_state": status.json()["state"],
                    "readiness": ready.json(),
                    "graph_status": graph.status_code,
                    "search_status": search.status_code,
                    "nodes": graph.json().get("node_count"),
                    "edges": graph.json().get("edge_count"),
                    "cgroup_peak_bytes": int((cgroup / "memory.peak").read_text()),
                    "cpu": dict(
                        row.split()
                        for row in (cgroup / "cpu.stat").read_text().splitlines()
                    ),
                }
            ),
            flush=True,
        )
        assert graph.is_success and search.is_success


if __name__ == "__main__":
    asyncio.run(main())
