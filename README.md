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
| `REPOBRAIN_DATABASE_URL` | Compose supplies a disposable local URL | `postgresql+asyncpg://USER:PASSWORD@HOST:5432/DATABASE`. Required for migrations. |
| `REPOBRAIN_DB_POOL_SIZE` | `5` | Persistent pooled connections per process, at least 1 |
| `REPOBRAIN_DB_MAX_OVERFLOW` | `5` | Additional connections per process, at least 0 |
| `REPOBRAIN_DB_POOL_TIMEOUT` | `10` | Positive pool checkout timeout in seconds |
| `REPOBRAIN_HOST_PORT` | `8000` | Compose backend port on `127.0.0.1` |
| `POSTGRES_PASSWORD` | Disposable Compose development password | Initial local database password |

Percent-encode special characters in database URL credentials. The Compose
defaults are for disposable development use only. For other deployments use
separately provisioned credentials and inject them through environment secrets.
Set both `POSTGRES_PASSWORD` and the matching `REPOBRAIN_DATABASE_URL` if
overriding the password on first local startup. PostgreSQL reads the initialization
password only when creating a new data directory.

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
