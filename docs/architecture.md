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
planned capabilities. Milestone 1 has no database or external AI dependency.
