# RepoBrain architecture

## Milestone 1

RepoBrain runs as a single Python 3.12 service. The FastAPI application factory
assembles the HTTP API, validated environment settings, and request middleware.
The middleware attaches a request ID to responses and structured JSON logs.
Errors use a consistent JSON envelope. `GET /healthz` reports process health
without calling any external service.

uv locks dependencies for development, CI, and the multi-stage Docker build.
The runtime container runs as a non-root user and checks its own health over
HTTP. Compose publishes the service on a configurable loopback port. GitHub
Actions runs lint, formatting, type, and endpoint checks without service
credentials.

## Milestone 2A

PostgreSQL 17 runs on the private Compose network and stores development data in
a named volume. The initial Alembic revision installs pgvector. The schema does
not yet use vector columns. The API creates a pooled SQLAlchemy asyncpg engine
when a database URL is configured and disposes it on shutdown. Connections
open on demand, so `GET /healthz` remains a process-only check.

| Table | Identity and data |
| --- | --- |
| `repositories` | UUID and a unique lowercase GitHub owner/name pair |
| `repository_snapshots` | UUID, repository foreign key, immutable 40-character commit SHA, ingestion state, and timezone-aware timestamps |
| `source_files` | UUID, snapshot foreign key, normalized repository-relative path, SHA-256, language, line count, and source text |

The snapshot identity is unique per repository and commit. Source paths are
case-sensitive and unique within a snapshot. The composite unique indexes also
support snapshot and file lookup by their parent IDs. Foreign keys cascade
explicit parent deletions. The database accepts `pending`, `running`,
`completed`, and `failed` states. A snapshot trigger rejects identity changes
and updates the modification timestamp.

Run Alembic before starting a deployment. CI and local integration tests run
migrations against a separate fresh PostgreSQL instance with temporary
storage. Tests check schema drift, CRUD, and database constraints.

## Planned architecture

1. Resolve public Python GitHub repositories to immutable commit SHAs. Index
   source files and retain paths and line ranges at the pinned commit.
2. Parse Python source with the standard-library AST to build a dependency
   graph. Treat repository contents as untrusted input.
3. Retrieve source passages with lexical and vector search. Optionally expand
   the candidate set through bounded graph traversal.
4. Generate evidence-backed answers with citations that link to the pinned
   commit, file, and lines. Expose dependency relationships through a React
   explorer.
5. Evaluate hybrid retrieval with and without graph expansion on the same
   pinned repositories and questions.

Indexing, graph storage, retrieval, answer generation, and the explorer are
planned capabilities. The backend has no external AI dependency.
