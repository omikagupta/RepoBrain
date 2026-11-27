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

## Milestone 2B

The ingestion API resolves a public GitHub repository and ref to a full commit
SHA. It reads that commit's Git tree and requests eligible blobs by immutable
ID from `api.github.com`. The worker never extracts archives, follows
redirects, or invokes Git. Streaming response budgets and bounded concurrency
limit memory and network use. Files remain in memory until the worker writes
them in a transaction with the completion transition.

PostgreSQL uniqueness and row locks deduplicate submissions across concurrent
requests. Updates check the active attempt's timestamp so an expired worker
cannot complete a retried job. Interrupted jobs can be retried under the same
snapshot UUID. The worker runs in the FastAPI lifespan and is intended for
one backend process.

## Milestone 3A

The graph CLI takes an already completed snapshot UUID. PostgreSQL holds a
snapshot row lock while the CLI reads its Python files and runs Python 3.12's
standard-library AST parser in a separate process. The process never imports
or evaluates the indexed source. A successful transaction writes a
`graph_analyses` summary with counts and diagnostics, `graph_nodes` with
symbol metadata, and `graph_edges` with relationship and source provenance.
The summary also marks empty graphs as complete. Concurrent repeats reuse
that summary. The CLI leaves existing graphs intact.

Nodes are keyed by a hash of file path, node kind, qualified name, and
source coordinates. Edges key on both nodes, relationship, and provenance
coordinates. UUIDs are derived from those keys and the snapshot UUID.
Composite foreign keys enforce that a node's file and both ends of an edge
belong to the same snapshot. The snapshot's immutable SHA pins the graph.
Inclusive line ranges refer to the original stored source. Definition spans
include decorators, and async definitions carry a flag.

- `CONTAINS` records lexical containment, including nested definitions.
- `IMPORTS` records unique local module candidates in conventional packages
  with `__init__.py`. A top-level directory named `src` without its own
  `__init__.py` is an additional source root. Colliding names or package
  prefixes are ambiguous. Relative imports require a unique package context.
- `IMPORTS_SYMBOL` covers direct `from` imports of unique undecorated
  top-level functions in modules consisting of plain function definitions
  and an optional docstring. Defaults, annotations, and a competing
  submodule prevent inference. `from package import name` can still yield
  an edge to the package when the imported name is unresolved.

Imports describe static candidates. Namespace packages, dynamic imports,
re-exports, arbitrary calls, and runtime dispatch are outside this analysis.
Syntax errors retain a module node and a path/line diagnostic, without
adding definitions for that file. Counts distinguish parsed files from
module nodes.

The CLI bounds a run to 45 seconds and accepts at most 1,000 files, 256 KiB
per file, and 4 MiB of source total. Limits also cover 300,000 AST nodes,
20,000 import statements, 20,000 graph nodes, 40,000 edges, and 4,000
diagnostics. Symbol names and import labels are limited to 1 KiB.
Exceeding a limit aborts the transaction.

## Milestone 3B

The graph exploration router reads graph summaries, nodes, edges,
neighborhoods, and source windows from the existing PostgreSQL tables.
Queries filter by snapshot UUID and check the committed analysis marker
before serving graph data. Source windows use completed ingestion data
independently of the analysis marker. The API does not write or rebuild
graphs.

Node and edge pages use the snapshot/stable-key unique indexes for keyset
pagination. A process-local HMAC binds each cursor to its resource, snapshot,
and active filters. Neighborhood traversal uses one bounded edge query per
frontier and one batched node query. It returns a deterministic partial result
when it would exceed 100 nodes or 200 edges.

Source evidence exposes an inclusive line window and the full file's SHA-256.
The byte cap bounds serialized line data, and source outside the window is
excluded from the response. Permalinks use canonical stored repository
identity, an immutable SHA, a safely encoded path, and the actual returned
line range. No API call to GitHub is needed.

## Planned architecture

1. Retrieve source passages with lexical and vector search. Optionally expand
   the candidate set through bounded graph traversal.
2. Generate evidence-backed answers with citations that link to the pinned
   commit, file, and lines. Expose dependency relationships through a React
   explorer.
3. Evaluate hybrid retrieval with and without graph expansion on the same
   pinned repositories and questions.

Retrieval, answer generation, and the explorer are
planned capabilities. The backend has no external AI dependency.
