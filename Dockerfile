FROM ghcr.io/astral-sh/uv:0.13.10 AS uv
FROM python:3.12-slim-bookworm AS builder

COPY --from=uv /uv /usr/local/bin/uv
WORKDIR /app
ENV UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-install-project
COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv uv sync --locked --no-dev --no-editable

FROM python:3.12-slim-bookworm AS runtime
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
RUN groupadd --gid 10001 app && useradd --uid 10001 --gid 10001 --no-create-home app
COPY --from=builder /app/.venv /app/.venv
USER 10001:10001
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python", "-c", "import json, sys, urllib.request; response = urllib.request.urlopen('http://127.0.0.1:8000/healthz', timeout=2); sys.exit(json.load(response) != {'status': 'healthy'})"]
CMD ["uvicorn", "repobrain.main:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--no-access-log"]
