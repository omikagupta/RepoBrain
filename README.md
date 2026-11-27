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
