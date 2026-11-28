# Deploying RepoBrain privately

RepoBrain's current security boundary is a single trusted operator. Start
with the loopback-only Compose configuration documented in the README.
Leave generation unset while preparing or demonstrating public snapshots.
Keep PostgreSQL on the internal Compose network and publish neither Docker
socket access nor a database listener.

Apply `compose.private.yaml` last with a unique `POSTGRES_PASSWORD`.
It removes the backend host port and generation credentials from the
effective configuration, applies resource limits, and leaves only the
loopback frontend port available. Initialize migrations before serving
requests. Use an existing authenticated HTTPS gateway for remote access.

With the password already set in the operator environment, start from the
repository root in PowerShell.

```powershell
$private = @('-f', 'compose.yaml', '-f', 'compose.frontend.yaml', '-f', 'compose.private.yaml')
docker compose @private up -d --wait db
docker compose @private run --rm --no-deps backend alembic upgrade head
docker compose @private up -d --wait --build frontend
Invoke-WebRequest http://127.0.0.1:8080/frontend-health
```

Stop if migration fails. On a newly migrated empty database, a same-origin
request for an unknown snapshot should return HTTP 404. The frontend health
check alone only verifies the static server.

For private remote access, place the frontend behind an authenticated HTTPS
gateway or a private network. Keep the frontend and API on the same origin.
Enforce authentication and an allowlist before forwarding any request to
RepoBrain. Restrict ingestion and generation to authorized operators. Apply
separate request and concurrency limits at the gateway, and reserve a hard
provider spending limit or use a local provider. The backend generation gate
limits concurrent work per process. It does not enforce user budgets.

For a demonstration using prepared snapshots, disable the provider and have
the gateway deny POST requests. Permit only GET and HEAD to the workspace and
the snapshot, search, graph and source routes used by the demo. Treat source
from public snapshots as untrusted text. A demo still needs request limits
and access control. Use the local Playwright fixture to demonstrate the
answer workflow without enabling real generation.

## Operations

- Keep credentials in the operator environment or a deployment secret store.
  Use a unique database password and rotate it through the database before
  changing the runtime configuration.
- Use the existing non-root images and health checks. Set CPU, memory and
  process ceilings for each service after measuring an isolated workload.
- Preserve the database volume. Back up with `pg_dump -Fc` to protected storage
  and restore to an isolated PostgreSQL instance with pgvector installed.
  Verify the restored snapshot and schema before any cutover. Follow the
  migration safety rules in AGENTS.md.
- Keep application request IDs and status codes. Exclude request bodies,
  questions, source excerpts, credentials and raw query strings from gateway
  and application logs.

This is a preparation guide. The authenticated gateway, per-user quotas,
backup restoration drill and public deployment have yet to be verified.
