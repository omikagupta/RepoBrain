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

## Milestone 4A

The lexical CLI uses the existing isolated Python parser to obtain definition
spans from stored source, independently of graph persistence. Version
`python-lines-v1` partitions files into disjoint line ranges around classes,
methods and functions, while keeping nested definitions inside a fitting
function or method. Gaps and oversized ranges fall back to consecutive
windows of at most 80 lines and 8 KiB. Overlap is zero. Blank lines and original
LF, CRLF or CR terminators are retained. Empty files produce no chunks.
Syntax-error files use the same fallback windows. A single line exceeding the
byte budget fails the build so source is never silently dropped.

Natural keys hash the snapshot ID, original path, inclusive boundaries, and
chunking version. UUIDs derive from those keys. `search_indexes` records the
committed version, file and chunk counts, source bytes, and build time.
`source_chunks` records the file ID, both SHA-256 hashes, exact source, and
normalized token data. Composite foreign keys enforce matching snapshot and
version, including the source file's snapshot. A stored generated `tsvector`
uses the PostgreSQL `simple` configuration and a GIN index supports matching.

A snapshot row lock serializes concurrent builds. The marker and all chunks
commit together. Retrying a failed build starts fresh. A completed build is
reused, and a different version fails clearly. Changes to chunk boundaries or
tokenization require an explicit version change. Builds share the graph
reader's limits of 1,000 files, 256 KiB per file, and 4 MiB of input, and stop
at 10,000 chunks or a 60-second timeout. Each token document has a 64 KiB cap.

Indexing case-folds words, preserves whole snake_case and dotted identifiers,
and adds their components. The chunk at a definition's first line also
receives its AST-qualified name and dotted suffixes. Each term is encoded as
one ASCII lexeme so PostgreSQL preserves its underscores, dots, and Unicode
identity. Terms longer than 128 UTF-8 bytes are skipped. Queries require
all distinct whole terms through parameterized `plainto_tsquery`.
Ranking uses `ts_rank(vector, query, 32)` in descending order with no separate
exact-match boost. Ties use bytewise path order, starting line, then stable
key. AST aliases are ordinary indexed occurrences and can affect term
frequency. Comments and strings are searchable. Stemming, fuzzy matches,
phrase syntax, semantic similarity, and cross-chunk matching are outside
this baseline.

The local fixture in `tests/test_lexical_search.py` builds seven chunks from
four nonempty Python files. The PostgreSQL integration test checks ordering,
matching, and byte-exact evidence. A PostgreSQL 17 run returned these results
for `load_item`.

| Rank | File | Lines | Score |
| ---: | --- | --- | ---: |
| 1 | `src/pkg/tools.py` | 4–8 | 0.07062409818172455 |
| 2 | `examples/a.py` | 1 | 0.057308755815029144 |
| 3 | `examples/é #?%.py` | 1 | 0.057308755815029144 |

## Milestone 4B

The optional local provider uses the upstream
[Jina code embedding model](https://huggingface.co/jinaai/jina-embeddings-v2-base-code)
at revision `516f4baf13dec4ddddda8631e019b5737c8bc250`, licensed Apache-2.0.
Its model card describes joint natural-language and programming-language
embeddings and recommends attention-mask mean pooling. The provider uses
the pinned quantized ONNX graph with one raw-text policy for documents and
queries, truncates at 512 tokenizer tokens including special tokens, and
L2-normalizes the 768-dimensional result. It loads verified local data
files through ONNX Runtime and Tokenizers, without a model download or
dynamic model-code loading. The optional Python dependencies are pinned in
`pyproject.toml` and `uv.lock`.

We chose the upstream quantized code checkpoint over
[BGE Small English](https://huggingface.co/BAAI/bge-small-en-v1.5) because
Jina documents training for code and natural-language retrieval. BGE Small
has fewer dimensions and is a useful general-text alternative. The
selection does not imply a measured relevance or speed advantage.

The model artifacts occupy about 165 MB on disk. Inference uses CPU only,
with two intra-op threads, one inter-op thread, a maximum batch of eight,
and one active operation per provider. Two more operations may wait in order;
additional requests receive HTTP 503. It also needs RAM for the ONNX
session and activations. Model startup is lazy. The 60-second deadline
covers both waiting and inference. A cancelled or timed-out active call
requests ONNX termination and keeps its slot until the native call returns.
Outputs may differ slightly across CPU architectures and
package or runtime versions. The model hashes, runtime pins, token policy,
and index metadata make the setup reproducible without guaranteeing
bit-identical floating-point results across machines.

`vector_indexes` records the snapshot, lexical and vector versions,
model ID and revision, dimension, encoding policy, chunk count, and
completion time. Each `chunk_embeddings` row references a persisted
lexical chunk through composite foreign keys that enforce snapshot and
version consistency. The builder reads at most 1,000 existing chunks,
computes embeddings outside the database transaction, then verifies the
input identities and hashes under a snapshot row lock before publishing
the marker and vectors atomically. A build has a ten-minute deadline.
Concurrent builders can duplicate inference, but only one publishes.
Completed indexes are checked for exact compatibility and reused.

The API searches one snapshot and version using exact pgvector cosine
distance, returning `1 - distance`. A B-tree supports scoping before the
bounded exact scan. Equal distances use bytewise path, starting line, and
stable chunk key to break ties. The response reuses persisted lexical
evidence and its source hashes. Inference runs without a database
transaction. The API revalidates the index and reads ranked evidence in
one fresh read-only transaction, returning HTTP 409 if the index changed.
There is no approximate index, relevance
threshold, reranking, or score fusion. Long chunks can lose model context
to tokenizer truncation while their returned evidence remains intact.

The synthetic corpus in `tests/test_vector_retrieval.py` uses a deterministic
two-coordinate fake provider padded to 768 dimensions. PostgreSQL ranked
`a.py` and `src/é #%.py` at 1.0, `near.py` at approximately 0.6, and
`far.py` at −1.0. This checks cosine semantics, tie-breaking, and evidence
identity. It measures no real-model quality.

In a separate CPU smoke test, the real model indexed two chunks and ranked
`reader.py` (0.6292623281478882) ahead of `math.py` (−0.04928473383188248)
for “read text from a file path.” This verifies the provisioned model, CLI,
and API together on a two-file example.

## Milestone 4C

Hybrid search reuses the standalone PostgreSQL ranking queries and chunk
evidence. It introduces no schema or index changes. Both indexes must be
complete, agree on chunk count and chunking version, and match the supported
vector version and the configured model identity, revision, dimension, and
encoding policy.

The service checks both indexes in a read-only repeatable-read transaction.
It closes that transaction before computing the query embedding. A fresh
read-only repeatable-read transaction verifies the snapshot identity, index
completion markers, counts, and compatibility before reading both candidate
lists and the matching evidence. Changed or missing index metadata fails the
request before fusion. Empty indexes require no inference.

Policy `rrf-v1` reads up to 30 candidates from each channel independently of the
requested result limit. It deduplicates by chunk UUID and sums
`1 / (60 + rank)` for each channel where the chunk appears. Ranks start at one,
both weights are one, and absent channels contribute zero without changing
either weight. Raw lexical and cosine scores are retained for diagnostics.
Fusion computes and compares exact fractions before serializing scores as
JSON numbers. Equal scores are ordered by bytewise UTF-8 path, starting line,
and stable chunk key. The first requested results receive consecutive ranks.

Valid lexical queries without matches use a vector-only candidate list. Queries
with no lexical terms receive HTTP 422. There is no cosine relevance threshold,
so even low-similarity candidates can appear. Pool limits can exclude otherwise
relevant chunks. Reproduction requires the same snapshot, indexes, model,
encoding policy, and fusion policy. The deterministic fake-provider fixture in
`tests/test_hybrid_search.py` checks exact scores derived from both baseline
ranks, result order, and evidence identity. It does not measure retrieval quality.

## Planned architecture

1. Expand the hybrid candidate set through bounded graph traversal.
2. Generate evidence-backed answers with citations that link to the pinned
   commit, file, and lines. Expose dependency relationships through a React
   explorer.
3. Evaluate hybrid retrieval with and without graph expansion on the same
   pinned repositories and questions.

Graph expansion, answer generation, and the explorer are planned capabilities.
The backend has no external AI dependency.
