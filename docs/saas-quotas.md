# Hosted quotas and preparation

Hosted defaults are three distinct repositories per workspace, up to 100
eligible Python files per new snapshot, five admitted ingestion submissions
per UTC day, and 30 admitted lexical requests per UTC hour. Graph and
source routes share 120 requests per hour. Existing identities have a
60-request UTC-minute limit. Settings are listed in `.env.example`.
Local single-operator behavior remains available.

Persistent counters use the stable owner UUID, so deleting and recreating
a workspace does not reset the budget. Each counter retains one row per
owner and operation and is overwritten on the next window. Closing an
account retains its small counters and the existing UUID tombstone.
Successful reservations consume the daily budget before GitHub resolution.
Cached snapshots, retries, provider failures, and cancelled admitted
jobs count. Requests denied before reservation consume no ingestion
allowance. Repository grants are idempotent per snapshot. An overlapping
submission is rejected with HTTP 429 and a retry delay, even if its
repository and ref match the active submission.

The default global concurrency is one ingestion, configurable to two.
One owner can hold one lease. An advisory transaction lock serializes
admission across processes. The lease covers resolution, collection and
optional index preparation. Normal completion, failure and cancellation
release the lease. A crash or interrupted release recovers on expiry
after twice the configured ingestion deadline plus 120 seconds. Lease
tokens fence old cleanup from releasing a newer job. Workspace mutation
locks and revisions still prevent in-flight submissions from restoring
removed grants. Public cached source and derived indexes remain intact.

The pre-authentication gate admits up to eight in-flight non-health
requests without queuing, with a separate health budget. Each gate group
allows 180 requests per local process minute, including unauthenticated
attempts. Oversized queries and bodies are rejected, with an 8 KiB cap.
The app buffers at most 8 KiB before routing and checks both declared and
actual request size. The body has a five-second deadline. The app buffers
responses up to 1 MiB, including responses without Content-Length, so an
oversized response fails before its headers reach the client. The hosted
profile is for bounded HTTP responses. Do not attach streaming routes to
it. Handlers have a 75-second deadline and response sends have a separate
five-second deadline. Hosted responses use Cache-Control: no-store.
The database pool has no overflow and at most two connections. Pool
saturation returns HTTP 429. GitHub throttling propagates a capped retry
delay and temporarily pauses new upstream work within each process.
GitHub metadata, refs, tree, and blob integrity remain checked by the
existing ingestion client.

## Optional index preparation

`REPOBRAIN_HOSTED_PREPARE_INDEXES=true` uses the same admitted task to run
the existing bounded graph and lexical builders after source ingestion
finishes. It holds its ingestion lease until both operations finish.
The builders commit separate idempotent readiness markers and use their
existing deadlines. Resubmitting a completed snapshot can retry missing
preparation. Ingestion completion and index readiness are distinct.
The default is off. Operators can use the existing CLI to populate indexes
on a suitably sized private machine and expose the prepared snapshots
through authorized grants. No ONNX or generation is used.

A production-image probe on Docker Desktop capped at 0.1 CPU and 512 MiB
processed 46 real Python files (253,700 bytes) over mocked GitHub transport
and disposable PostgreSQL. Import, fixture preparation and ASGI health
took 50.795 seconds. Ingestion and both index builds took 31.704 seconds.
The graph exposed 373 nodes and 327 edges, and lexical search returned
HTTP 200. Peak cgroup memory was 105,869,312 bytes and total CPU use was
10.365 seconds. These are single-run figures. The 100-file boundary,
network delays and concurrent load remain unverified, and cold startup
leaves little margin. Keep managed preparation off by default pending
additional validation. The probe is in `tests/hosted_runtime_probe.py`.

The hardening follow-up used a 96-file fixture assembled by repeating
real project source under distinct paths (518,643 bytes). With the same
0.1 CPU and 512 MiB container limits and mocked network latency, startup
through ASGI health took 38.602 seconds. Ingestion and both index builds
took 41.709 seconds. Peak cgroup memory was 107,745,280 bytes, total CPU
use was 9.551 seconds, and graph and lexical endpoints returned HTTP 200.
The graph had 758 nodes and 662 edges. This single run does not establish
performance for larger source bytes, live GitHub traffic or concurrent load.
Managed preparation remains opt-in.

Migration `0006_hosted_quotas` is forward-only and adds counters and leases.
Run the disposable PostgreSQL suite and Alembic drift checks before
promotion. Public deployment, a gateway-level abuse policy, hosted database
verification and a long-term retention and storage budget remain pending.
Process-local anonymous limits do not share state across replicas or
restarts.

## Cache storage and retention

Migration `0007_hosted_cache` marks only snapshots newly created through
hosted ingestion. Existing snapshots and frozen benchmark records are
never marked or pruned by this migration or retention logic. Defaults
reserve the configured maximum source bytes per new snapshot, with caps
of 40 tracked snapshots and 128 MiB of logical reservations. These caps
do not measure physical PostgreSQL storage, derived indexes, or WAL.
Monitor database size separately.

Optional pruning defaults off. Enable it only after explicit operator
approval and a verified backup. It reclaims at most ten tracked snapshots
per admission, only when they are ungranted and older than the retention
window (seven days by default). Grant creation and pruning share a
transaction lock. Newly claimed snapshots are touched so a bounded
collection or indexing job has time to finish. A storage denial returns
429. It preserves all existing grants and consumes an already-admitted
daily attempt. Existing or frozen data should remain outside the hosted
cache lifecycle. Keep research on its own database.

## Gateway preparation

`deploy/nginx/hosted-gateway.conf` is a local-tested template for a
dedicated TLS gateway. It caps API rate globally and per direct peer,
bounds concurrent connections and request bodies, and forwards API
traffic without retries. It ignores inbound forwarded addresses when
forming the outgoing client address. Terminate TLS with operator-provided
certificate files and replace the example host and auth origin. Keep the
backend, frontend upstream and database listeners private. If a trusted
load balancer fronts the gateway, configure its exact trusted proxy
addresses before relying on per-client limits. Supabase sign-in endpoints
are outside this gateway and require independent provider-side controls.
The template passed `nginx -t` with a local certificate. Public ingress,
production certificate renewal, and real proxy-chain behavior remain
unverified.
