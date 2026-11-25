# RepoBrain

RepoBrain is a research-oriented AI code intelligence platform.

Milestone 1 provides a Python 3.12 FastAPI backend, a health endpoint, validated
settings, and JSON request logging. The source is under `src/repobrain`.
See the [architecture overview](docs/architecture.md) for the current design and roadmap.

## Set up in Windows PowerShell

Run these commands from the repository root with Python 3.12 and uv installed.

```powershell
py -3.12 --version
uv --version
uv sync --locked --python 3.12
```

The backend starts with defaults. To customize logging, create a local `.env`
from `.env.example` if you do not already have one. The operating system
environment takes precedence over `.env`.

| Variable | Default | Allowed values |
| --- | --- | --- |
| `REPOBRAIN_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |

## Run locally

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
uv run --locked pytest
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
    sh -ec 'uv sync --locked && uv run --locked ruff check --no-cache . && uv run --locked ruff format --no-cache --check . && uv run --locked mypy --cache-dir /tmp/mypy-cache && uv run --locked pytest -p no:cacheprovider'
```

## Run in Docker Desktop

Start Docker Desktop's Linux engine. Compose binds port 8000 on loopback by
default.

```powershell
docker compose up --build --detach --wait
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/healthz | ConvertTo-Json -Compress
docker compose down
```

If port 8000 is occupied, run Compose on port 18080. The service and health
check still use port 8000 inside the container.

```powershell
$env:REPOBRAIN_HOST_PORT = '18080'
docker compose up --build --detach --wait
Invoke-RestMethod http://127.0.0.1:18080/healthz | ConvertTo-Json -Compress
docker compose down
Remove-Item Env:REPOBRAIN_HOST_PORT
```
