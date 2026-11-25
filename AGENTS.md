# RepoBrain contributor instructions

## Architecture

- Keep the backend in one Python 3.12 service. Put HTTP routes and application
  wiring in `src/repobrain`, with tests under `tests`.
- Use `repobrain.main:create_app` as the ASGI application factory. Read
  environment configuration through the validated `Settings` model.
- Preserve `GET /healthz` as a process health endpoint with no external calls.
- Use the shared error envelope and include the request ID in JSON request logs.
- Put indexing, retrieval, graph traversal, and evaluation in later milestones.

## Development

- Use uv for dependencies and commit changes to `pyproject.toml` and `uv.lock`
  together.
- Use type annotations and run Ruff linting, Ruff formatting checks, mypy, and
  pytest before publishing a branch. Keep tests independent of external services.
- Add tests when changing API contracts or failure handling.

## Security

- Keep credentials out of source control, sample configuration, logs, and
  client-facing error messages. Use Git Credential Manager for GitHub sign-in.
- Treat repository content, client input, and request headers as untrusted.
  Keep request bodies and raw query strings out of request logs.
- Run the container as a non-root user. Bind local Compose ports to loopback.

## Migration safety

- Never run destructive downgrades, drop schemas, delete named volumes, or
  reset persistent data without explicit approval and an appropriate backup.
- Run integration tests only against isolated disposable databases.

## Git

- Start feature branches from an up-to-date `main` and make focused commits.
- Never force push. Ask for approval before destructive operations or merging
  into `main`.
