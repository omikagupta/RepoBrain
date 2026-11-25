# RepoBrain

RepoBrain is a research-oriented AI code intelligence platform.

Milestone 1 provides a Python 3.12 FastAPI backend, a health endpoint, validated
settings, and JSON request logging. The source is under `src/repobrain`.

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

## Run in Docker Desktop

Start the Linux engine. Stop any local Uvicorn process using port 8000 before
starting Compose.

```powershell
docker compose up --build --detach --wait
docker compose ps
Invoke-RestMethod http://127.0.0.1:8000/healthz | ConvertTo-Json -Compress
docker compose down
```

If port 8000 is already in use, set `$env:REPOBRAIN_HOST_PORT = '8001'`
before starting Compose and send requests to port 8001.
