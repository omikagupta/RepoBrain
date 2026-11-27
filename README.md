# RepoBrain

RepoBrain is a research-oriented AI code intelligence platform.

RepoBrain provides a Python 3.12 FastAPI backend and PostgreSQL persistence
for repositories, commit snapshots, and source files. The source is under
`src/repobrain`.
See the [architecture overview](docs/architecture.md) for the current design and roadmap.

## Set up in Windows PowerShell

Run these commands from the repository root with Python 3.12 and uv installed.

```powershell
py -3.12 --version
uv --version
uv sync --locked --python 3.12
```

To customize settings, create a local `.env` from `.env.example` if you do not
already have one. The operating system environment takes precedence over
`.env`.

| Variable | Default | Allowed values |
| --- | --- | --- |
| `REPOBRAIN_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| `REPOBRAIN_DATABASE_URL` | Unset | `postgresql+asyncpg://USER:PASSWORD@HOST:5432/DATABASE` for a separately hosted database |
| `REPOBRAIN_DB_POOL_SIZE` | `5` | Persistent pooled connections per process, at least 1 |
| `REPOBRAIN_DB_MAX_OVERFLOW` | `5` | Additional connections per process, at least 0 |
| `REPOBRAIN_DB_POOL_TIMEOUT` | `10` | Positive pool checkout timeout in seconds |
| `REPOBRAIN_HOST_PORT` | `8000` | Compose backend port on `127.0.0.1` |
| `POSTGRES_PASSWORD` | Disposable Compose development password | Initial local database password |

For local Compose, set only `POSTGRES_PASSWORD` before creating a new data
volume. Supply the raw password. Compose passes the same value to PostgreSQL
and the backend, and the backend encodes it for the connection URL. The
disposable development default applies when the variable is unset or empty.
Changing it later does not rotate the password in an existing volume. If the
configured password does not match the stored one, PostgreSQL's authenticated
health check fails. Restore the matching value or arrange a deliberate rotation.

For a separately hosted database, provide `REPOBRAIN_DATABASE_URL` outside this
Compose stack. Percent-encode special characters in URL credentials and inject
the URL through your environment's secret store.

## Run locally

To exercise the HTTP API without PostgreSQL, leave `REPOBRAIN_DATABASE_URL` unset.

```powershell
uv run --locked uvicorn repobrain.main:create_app --factory --reload --no-access-log
```

From another terminal, check the service.

```powershell
Invoke-RestMethod http://127.0.0.1:8000/healthz | ConvertTo-Json -Compress
```

The endpoint returns HTTP 200 with `{"status":"healthy"}`. Responses include
`X-Request-ID`. Errors include `code`, `message`, and `request_id` in an
`error` object. The OpenAPI UI is available at
[localhost:8000/docs](http://127.0.0.1:8000/docs).

## Run checks

```powershell
uv run --locked ruff check .
uv run --locked ruff format --check .
uv run --locked mypy
uv run --locked pytest -m "not postgres"
```

### Run checks in Docker Desktop

If Windows Application Control blocks native development tools, leave the
security controls enabled and run the checks in a Linux container. Start Docker
Desktop's Linux engine, then run these commands from the repository root in
PowerShell. The checkout is mounted read-only and the container keeps the test
environment and caches in its temporary filesystem.

```powershell
docker build --target builder --tag repobrain-checks .
if ($LASTEXITCODE -ne 0) { throw 'Docker test image build failed' }
$workspace = (Get-Location).Path
docker run --rm --mount "type=bind,source=$workspace,target=/workspace,readonly" `
    --workdir /workspace --env UV_PROJECT_ENVIRONMENT=/tmp/repobrain-venv `
    --env PYTHONDONTWRITEBYTECODE=1 repobrain-checks `
    sh -ec 'uv sync --locked && uv run --locked ruff check --no-cache . && uv run --locked ruff format --no-cache --check . && uv run --locked mypy --cache-dir /tmp/mypy-cache && uv run --locked pytest -m "not postgres" -p no:cacheprovider'
```

### Run PostgreSQL integration tests

The test stack starts a separate PostgreSQL instance on a private network. Its
data directory uses temporary memory-backed storage and the migration fixture
requires an empty database named `repobrain_test`. The normal development
volume is outside this stack.

```powershell
docker compose -f compose.test.yaml up --build --abort-on-container-exit --exit-code-from tests
$testExit = $LASTEXITCODE
docker compose -f compose.test.yaml down
if ($testExit -ne 0) { throw "PostgreSQL integration tests failed ($testExit)" }
```

## Run in Docker Desktop

Start Docker Desktop's Linux engine. Compose publishes the backend on loopback
and keeps PostgreSQL on the Compose network. Initialize or update the schema
before starting the backend.

```powershell
docker compose up --detach --wait db
docker compose build backend
docker compose run --rm --no-deps backend alembic upgrade head
docker compose run --rm --no-deps backend alembic current
docker compose up --detach --wait backend
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/healthz | ConvertTo-Json -Compress
docker compose down
```

If port 8000 is occupied, run Compose on port 18080. The service and health
check still use port 8000 inside the container.

```powershell
$env:REPOBRAIN_HOST_PORT = '18080'
docker compose up --detach --wait db
docker compose build backend
docker compose run --rm --no-deps backend alembic upgrade head
docker compose up --detach --wait backend
Invoke-RestMethod http://127.0.0.1:18080/healthz | ConvertTo-Json -Compress
docker compose down
Remove-Item Env:REPOBRAIN_HOST_PORT
```

`docker compose down` stops the services and preserves the named
`postgres_data` volume. Apply later migrations with the same
`alembic upgrade head` command. To migrate a separately hosted database from
PowerShell, provide `REPOBRAIN_DATABASE_URL` through your environment and run
`uv run --locked alembic upgrade head`. The migration role needs schema DDL
privileges and permission to enable `vector`, or an administrator can enable
the extension first.

### Migration safety

Never run destructive downgrades, drop schemas, delete named volumes, or reset
persistent data without explicit approval and an appropriate backup.
Integration tests must use only isolated disposable databases.

## Ingest a public GitHub repository

Start the migrated Compose stack using the commands above. Use `owner/name`
only. Omit `ref` to resolve the repository's current default branch. You can
also supply a branch, tag, fully qualified ref such as `refs/tags/v1`, or a
full 40-character commit SHA.

```powershell
$base = 'http://127.0.0.1:8000'
$body = @{ repository = 'pallets/click'; ref = '8.1.8' } | ConvertTo-Json
$job = Invoke-RestMethod -Method Post -Uri "$base/api/v1/repositories/ingestions" `
    -ContentType 'application/json' -Body $body
Invoke-RestMethod "$base/api/v1/ingestions/$($job.snapshot_id)"
```

POST resolves the ref before returning `202` with the snapshot ID and a
`Location` header. Repeat GET until the snapshot is `completed` or `failed`.
POST returns `200` for a completed snapshot at the same commit. To retry a
failed snapshot, submit the same repository with its resolved SHA. Submitting
a branch again may resolve a newer commit. A full worker returns `429`; retry
later or continue polling an already known snapshot. GitHub rate limits return
`503` during resolution or fail an accepted job during fetching.

To inspect the stored paths and hashes, restrict the query to the returned
snapshot UUID. Run it from PowerShell with the development database running.

```powershell
$snapshot = ([guid]$job.snapshot_id).ToString()
docker compose exec -T db psql -U repobrain -d repobrain -c "SELECT path, content_sha256, line_count FROM source_files WHERE snapshot_id = '$snapshot' ORDER BY path;"
```

### Limits and worker behavior

Set these variables in the environment or local Compose `.env`.

| Variable | Default | Applies to |
| --- | ---: | --- |
| `REPOBRAIN_INGESTION_MAX_FILES` | 200 | Candidate Python files after path and size filtering |
| `REPOBRAIN_INGESTION_MAX_FILE_BYTES` | 262144 | Maximum file size in bytes |
| `REPOBRAIN_INGESTION_MAX_TOTAL_BYTES` | 4194304 | Raw bytes retained, also bounding the next candidate download |
| `REPOBRAIN_INGESTION_MAX_NETWORK_BYTES` | 12582912 | Total response body bytes across GitHub metadata, tree, and blobs |
| `REPOBRAIN_INGESTION_TIMEOUT` | 60 | Seconds per phase for resolution and background ingestion |
| `REPOBRAIN_INGESTION_CONCURRENCY` | 1 | Concurrent submissions and jobs combined per process |

The worker moves from `pending` to `running` to `completed` or `failed`.
Source files and completion commit in one transaction. A graceful shutdown
cancels jobs and marks them failed. Polling or resubmitting marks an abandoned
active snapshot failed after the configured timeout plus 15 seconds. The MVP
uses one backend process and has no durable queue or automatic retries.

Requests go to the official GitHub REST API over HTTPS. The worker ignores
upstream URLs, rejects redirects, and sends no credentials. Each file comes
from the resolved commit's tree by immutable blob ID. Only regular lowercase
`.py` paths are eligible. Symlinks, submodules, oversized files, binary or
invalid UTF-8 files, and common vendor and generated directories are skipped.
Unsafe or duplicate paths and truncated trees fail the job. Source text is
decoded as strict UTF-8 with no newline normalization. SHA-256 covers the
original bytes. Line counts treat LF, CRLF, and bare CR as line breaks and
include a final unterminated line. All tests use local GitHub fixtures.

## Analyze a completed snapshot

Migrate the database to Alembic head first. Use the snapshot UUID returned
by ingestion. This explicit command reads stored Python source and prints
the pinned commit SHA, file and graph counts, and the diagnostic count.

```powershell
$snapshot = ([guid]$job.snapshot_id).ToString()
docker compose run --rm --no-deps backend python -m repobrain.graph $snapshot
docker compose exec -T db psql -U repobrain -d repobrain -c "SELECT kind, qualified_name, start_line, end_line FROM graph_nodes WHERE snapshot_id = '$snapshot' ORDER BY stable_key;"
docker compose exec -T db psql -U repobrain -d repobrain -c "SELECT relationship, line, provenance FROM graph_edges WHERE snapshot_id = '$snapshot' ORDER BY stable_key;"
docker compose exec -T db psql -U repobrain -d repobrain -c "SELECT diagnostics FROM graph_analyses WHERE snapshot_id = '$snapshot';"
```

With an existing external database URL in the environment, you can also
run `uv run --locked python -m repobrain.graph $snapshot` from PowerShell.
Each analysis commits its summary, nodes, and edges together. Repeating the
command reuses the committed graph. Failed runs can be retried.

The analyzer supports lexical containment and conservative local imports in
regular packages at the repository root and under an unpackaged `src/`.
Symbol imports require a unique, plain top-level function in a module with no
other executable top-level statements. Unresolved imports and syntax errors
are recorded as diagnostics. See the
[architecture overview](docs/architecture.md#milestone-3a) for resolution
rules and analysis limits.

## Explore a snapshot graph

The following GET endpoints use `/api/v1/snapshots/{snapshot_id}` as their
prefix. The first four require a completed graph. A missing snapshot returns
`404`; an existing snapshot without an analysis returns
`409 graph_not_analyzed`. A successfully analyzed empty graph returns zero
counts and empty pages.

| Endpoint | Query parameters and result |
| --- | --- |
| `/graph` | Canonical repository, pinned SHA, counts and supported relationships |
| `/nodes` | `kind`, literal `qualified_name_prefix`, exact `path`, `limit`, `cursor`. Returns stable UUIDs, source spans, and async flags. |
| `/edges` | `relationship`, `source_id`, `target_id`, `limit`, `cursor`. Returns directed edges and stored provenance. |
| `/neighborhood` | `node_id` required, `direction` defaults to `both`, `depth` defaults to 1 and permits 2, optional repeated `relationship` |
| `/source` | Exact POSIX `path` required, optional inclusive `start_line` and `end_line`. Requires completed ingestion. |

```powershell
$graphBase = "$base/api/v1/snapshots/$snapshot"
Invoke-RestMethod "$graphBase/graph"
$page = Invoke-RestMethod "$graphBase/nodes?kind=function&limit=25"
if ($page.next_cursor) {
    $cursor = [uri]::EscapeDataString($page.next_cursor)
    Invoke-RestMethod "$graphBase/nodes?kind=function&limit=25&cursor=$cursor"
}
if ($page.items.Count -gt 0) {
    $node = $page.items[0].id
    Invoke-RestMethod "$graphBase/edges?source_id=$node"
    Invoke-RestMethod "$graphBase/neighborhood?node_id=$node&direction=outgoing&depth=2"
    $path = [uri]::EscapeDataString($page.items[0].path)
    Invoke-RestMethod "$graphBase/source?path=$path&start_line=1&end_line=10"
}
```

Node and edge pages use ascending stable keys. `limit` defaults to 50 and
permits 1–100. Reuse `next_cursor` with the original snapshot, endpoint, and
filters. You can change the page size. Cursors are opaque and valid for the
backend process that issued them. Restart pagination after a process restart
or an invalid cursor response.

Neighborhoods are breadth-first and include the center. They follow incoming,
outgoing, or both directions while preserving each edge's original direction.
The response contains up to 100 nodes and 200 edges. On reaching either cap,
it returns a deterministic partial graph with `truncated: true`.

Source responses return stored text with original line numbers and a SHA-256
for the complete stored file. The default window starts at line 1 and returns
at most 200 lines. Supplying only a start line shifts that window. A requested
end beyond EOF is clipped. The response rejects windows over 200 lines or
64 KiB of serialized line data, and rejects starts beyond EOF for nonempty
files. It omits newline terminators while recognizing LF, CRLF, and bare CR.
An empty file returns no lines, null actual range bounds, and a file link
without a line fragment. The permalink is constructed from the verified
stored repository, exact commit and encoded path, with the actual range in
the fragment. The backend makes no live GitHub request to check whether the
link is still accessible.

## Build and query a lexical index

Apply Alembic head and start the Compose backend. Use a completed ingestion
snapshot UUID. The index build uses its stored source and does not require a
persisted graph. A repeated build reuses the committed index.

```powershell
$snapshot = ([guid]$job.snapshot_id).ToString()
docker compose run --rm --no-deps backend python -m repobrain.search $snapshot
$query = [uri]::EscapeDataString('load_item')
Invoke-RestMethod "$base/api/v1/snapshots/$snapshot/search/lexical?q=$query&limit=10"
```

With a database URL configured outside Compose, run
`uv run --locked python -m repobrain.search $snapshot` from PowerShell.
The API returns `404` for a missing snapshot, `409` for incomplete ingestion
or an unavailable compatible index, and `422` for invalid query parameters.
Queries accept up to 256 characters and 32 distinct supported terms.
`limit` defaults to 10 and permits 1–30.

Results include score, rank, source file and chunk UUIDs, exact UTF-8 chunk
text, both SHA-256 hashes, and a permalink for the pinned commit and
inclusive line range. Search uses exact case-folded tokens and a PostgreSQL
full-text score. The [architecture notes](docs/architecture.md#milestone-4a)
describe identifier handling, ranking, and build limits.

## Build and query a vector index

Vector search uses the Apache-2.0 model `jinaai/jina-embeddings-v2-base-code`
at revision `516f4baf13dec4ddddda8631e019b5737c8bc250`. The quantized ONNX
model runs on CPU and returns 768-dimensional embeddings. Install the
optional inference dependencies only where you build or query vector indexes.

```powershell
uv sync --locked --extra vector
```

Provision the two assets explicitly on a machine with network access. This
step downloads about 165 MB. You can copy the resulting directory to an
offline machine. RepoBrain verifies both files against pinned SHA-256 digests.

```powershell
$revision = '516f4baf13dec4ddddda8631e019b5737c8bc250'
$modelBase = "https://huggingface.co/jinaai/jina-embeddings-v2-base-code/resolve/$revision"
$modelDir = Join-Path (Get-Location) '.venv-uv-cache/jina-model'
New-Item -ItemType Directory -Force $modelDir | Out-Null
Invoke-WebRequest "$modelBase/tokenizer.json" -OutFile (Join-Path $modelDir 'tokenizer.json')
Invoke-WebRequest "$modelBase/onnx/model_quantized.onnx" -OutFile (Join-Path $modelDir 'model_quantized.onnx')
$env:REPOBRAIN_VECTOR_MODEL_DIR = (Resolve-Path $modelDir).Path
```

Apply Alembic head and build the snapshot's lexical index first. With a
database URL configured, run the vector build separately.

```powershell
$snapshot = ([guid]$job.snapshot_id).ToString()
uv run --locked --extra vector python -m repobrain.search.vector_cli $snapshot
```

For Docker, the optional Compose override installs CPU dependencies during
the image build and mounts the already provisioned assets read-only.

```powershell
docker compose -f compose.yaml -f compose.vector.yaml up -d --build
docker compose -f compose.yaml -f compose.vector.yaml run --rm --no-deps backend python -m repobrain.search.vector_cli $snapshot
$query = [uri]::EscapeDataString('read text from a file path')
Invoke-RestMethod "$base/api/v1/snapshots/$snapshot/search/vector?q=$query&limit=10"
```

The endpoint returns the original query, pinned repository and commit,
`model`, `chunking_version`, `vector_version`, and ranked `results`.
Each result includes the same chunk UUID, original text, hashes, and
permalink as its lexical counterpart. Scores are cosine similarity in
the range −1 to 1, with higher scores ranking first. A missing or incompatible
index returns `409`, unavailable inference returns `503`, and invalid
parameters return `422`. Empty completed indexes return empty results
without loading the model. See the
[vector architecture notes](docs/architecture.md#milestone-4b) for limits.

The following response excerpt comes from the deterministic fake-provider
fixture.

```json
{
  "query": "read from disk",
  "vector_version": "cosine-exact-v1",
  "metric": "cosine_similarity",
  "results": [
    {"rank": 1, "path": "a.py", "start_line": 1, "end_line": 1, "score": 1.0}
  ]
}
```

## Query both indexes with hybrid search

Build the lexical and vector indexes for the same completed snapshot using
the commands above. Use the vector-enabled backend and its pinned model assets.

```powershell
$query = [uri]::EscapeDataString('read_file')
$response = Invoke-RestMethod "$base/api/v1/snapshots/$snapshot/search/hybrid?q=$query&limit=10"
$response.results | Select-Object rank, path, score, lexical_rank, vector_rank, permalink
```

`q` accepts up to 256 characters and must produce 1–32 distinct lexical terms.
Punctuation-only queries return `422`. The `limit` is 1–30 and defaults to 10.
Missing snapshots return `404`. Incomplete ingestion or missing, incompatible,
or changed indexes return `409`. Unavailable inference returns `503`.
A valid query with no lexical matches can still return vector matches.
Two completed empty indexes return no hits and skip inference.

The response includes the original query, repository, pinned commit, snapshot
UUID, chunking and vector index versions, model metadata, and the `fusion` policy.
Each result includes the original chunk and source file UUIDs, text, hashes,
line range, pinned permalink, fused `rank` and `score`, and per-channel ranks,
scores, and attribution. An absent channel contributes zero and its rank and
score fields are null. The lexical and vector endpoints remain available as
independent baselines.

The [hybrid architecture notes](docs/architecture.md#milestone-4c) describe
the fixed ranking policy and deterministic test fixture.

## Query with graph-enhanced retrieval

Build both search indexes, then run the graph analyzer for the same completed
snapshot using the commands above. Use the vector-enabled backend.

```powershell
$query = [uri]::EscapeDataString('read_file')
$response = Invoke-RestMethod "$base/api/v1/snapshots/$snapshot/search/graph-enhanced?q=$query&limit=10"
$response.results | Select-Object rank, path, score, hybrid_rank, graph_contribution, permalink
$response.results | Where-Object provenance | ForEach-Object { $_.provenance }
$response.traversal
```

The endpoint uses the same query validation as hybrid search and accepts
`limit` from 1 to 30. Incomplete ingestion, unavailable or incompatible
indexes, or missing graph analysis return HTTP 409 before inference begins.
Changed metadata during inference also returns HTTP 409. An unavailable
embedding provider returns HTTP 503.

The response records the pinned snapshot, embedding and index metadata,
fusion and expansion policies, and traversal counts and truncation flags.
Each hit includes its fused score, original hybrid score and rank when
present, and at most one graph path with directed edges, node IDs and seed
identity. Truncation returns the bounded partial expansion with HTTP 200.
See the [graph retrieval policy](docs/architecture.md#milestone-5a).

In the synthetic `read_file` fixture, `a.py` ranks first. Its persisted import
edges add `x_bridge.py` and the module and helper chunks in `z_dependency.py`
at ranks 2–4. Each gets a graph contribution of `3/122`. The fixture uses fake
embeddings and checks graph paths and exact citations. Retrieval quality
remains unevaluated.

## Generate an answer from pinned source evidence

Configure a trusted OpenAI-compatible chat-completions endpoint and an
explicit model. The endpoint must support `response_format: json_object`
and `max_tokens`. HTTPS is required except for HTTP on literal loopback
addresses. With Docker, the address must be reachable from the backend
container. Set the API key in the process environment when the provider
requires it. Keep secrets out of project files and terminal output.

```powershell
$env:REPOBRAIN_GENERATION_ENDPOINT = 'https://llm.example.invalid/v1/chat/completions'
$env:REPOBRAIN_GENERATION_MODEL = 'your-configured-model'
$env:REPOBRAIN_GENERATION_TIMEOUT = '30'
$env:REPOBRAIN_GENERATION_CONCURRENCY = '2'
# Use the actual trusted endpoint and model before restarting the backend.
docker compose -f compose.yaml -f compose.vector.yaml up -d backend
$body = @{ question = 'How does repository ingestion work?'; retrieval_mode = 'graph-enhanced' } | ConvertTo-Json
$answer = Invoke-RestMethod -Method Post -ContentType 'application/json' -Body $body -Uri "$base/api/v1/snapshots/$snapshot/answer"
$answer.claims
$answer.citations | Select-Object citation_id, path, start_line, end_line, permalink
```

Choose `lexical`, `vector`, `hybrid`, or `graph-enhanced` (default). Build the
required indexes and graph as for the search endpoints. Generation requires
no live provider for tests or for retrieval-only development. You can use
a compatible local model or run the offline test suite with disposable
PostgreSQL. RepoBrain never downloads a generation model.

The context preserves complete source chunks and their order, with up to 20
retrieved candidates, 12 included chunks and 32 KiB of serialized evidence.
The model gets citation IDs, paths, line ranges, exact text, and graph
relationship types when available. Hashes, links, scores, snapshot identity,
and full provenance stay server-side for citation resolution.
The provider request body is bounded to 96 KiB, with a 256-character question
limit and a 1,500-token output request limit. An empty usable context returns
`insufficient_evidence` without calling the model. With usable evidence, an
unconfigured, busy, or rate-limited provider returns HTTP 503. Timeout
returns 504. Invalid provider responses or citations return 502.

The synthetic fixture's deterministic provider returns the following claim
fields. Canonical evidence in that response links E1 to `a.py#L1-L2` and E2 to
`z_dependency.py#L1-L2` on the exact stored commit.

```json
{
  "status": "answered",
  "citation_status": "structurally_valid",
  "claims": [
    {"text": "The entry point imports a helper.", "kind": "observation", "citations": ["E1"]},
    {"text": "The helper returns the fixture string.", "kind": "observation", "citations": ["E2"]}
  ],
  "usage": null
}
```

A successful citation check guarantees that cited IDs resolve to evidence
actually sent to the model. Assessing whether the code supports a claim is
a separate task. RepoBrain provides no execution tools, and untrusted source
can still influence model behavior. See the
[answer architecture and limits](docs/architecture.md#milestone-5b).

The optional adapter sends the configured credential only as a bearer header.
Provider error bodies and wire diagnostics are kept out of logs and API
errors. Literal copies of the configured credential are rejected at the
prompt and response boundaries as a secondary safeguard. String matching
cannot reliably detect a model paraphrasing, encoding, or otherwise
transforming a secret. Use a trusted provider and configure credentials
only through the API key environment variable.
