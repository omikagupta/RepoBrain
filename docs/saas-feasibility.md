# Milestone 7 Phase 1 feasibility

Baseline is merged main at `3a36e87e70b8fa8f962bb40f8188c5e4be40b112`.
Measurements are from local Linux containers on Docker Desktop (x86-64,
14 visible CPUs and 8,042,917,888 bytes of VM RAM), using cached production
image builds from the Milestone 6B release checks. This is a feasibility
probe, with no hosted deployment or concurrency/load test.

| Measurement | Observation |
| --- | ---: |
| Standard backend image, Docker inspect | 245,002,594 bytes |
| Vector backend image, before model assets | 474,015,686 bytes |
| Pinned ONNX and tokenizer assets | 164,456,937 bytes |
| Frontend container image / static Vite output | 102,377,172 / 816,389 bytes |
| Base backend import, app construction and ASGI health at 1 CPU | 2.467 s wall, 2.922 s process CPU, 62,234,624 B cgroup peak |
| Base backend subprocess HTTP probe at 0.1 CPU | Did not reach health within the approximately 60 s polling window |
| Vector image subprocess HTTP probe at 0.1 CPU | Health returned 200 after 53.906 s, cgroup peak 89,157,632 B |
| First short embedding at 1 CPU / 512 MiB, FastAPI imported | 14.552 s wall, 9.04 s process CPU, 333,418,496 B cgroup peak |
| First short embedding at 0.1 CPU / 512 MiB, HTTP server running | 33.398 s wall, about 6.05 cgroup CPU seconds above health sample, 384,880,640 B cgroup peak |
| Repeated short embedding at same cap | 0.017 s wall, 0.034 s process CPU |
| Eight long inputs at the same cap | Container exited 137. The probe did not retain an OOM counter after exit. |
| Prepared local research database | 31,577,779 bytes, PostgreSQL 17.12, pgvector 0.8.7 |

The pinned Jina code model emits 768 dimensions and uses
`onnx-int8-mean-l2-512-v1`. The short probe used the production provider
with a read-only model mount and disabled network; startup health was
measured separately. Cold embedding initialization and indexing headroom
are insufficiently demonstrated for Render Free. Retain the existing local
retrieval methods and default to lexical search plus graph and source
exploration for the hosted beta. Make unavailable modes visible in the UI.

## Provider fit and eligibility

- Render Free supplies 0.1 CPU, 512 MB and 750 instance hours per workspace
  monthly. Free web services sleep after 15 minutes and lack persistent
  disks and one-off jobs. Static Sites support CDN delivery and SPA
  rewrites. Bandwidth and build allowances are shared. For a strict zero
  budget, use an eligible Hobby workspace without an attached payment
  method and accept suspension or paused builds at limits. Render requires
  capacity to enter a binding contract and prohibits use under 16.
  [Free service limits](https://render.com/docs/free) ·
  [Compute plans](https://render.com/docs/compute-plans) ·
  [Static Sites](https://render.com/docs/static-sites) ·
  [Render terms](https://render.com/terms)
- Supabase Free offers 500 MB database storage, 5 GB egress and 50,000
  monthly active users. It pauses projects after one week of inactivity.
  This is a storage and egress budget, not a capacity forecast for 50,000
  RepoBrain users. Supabase requires legal authority to accept its
  contract. Default email delivery is limited to project team addresses
  and two messages per hour. Prefer GitHub OAuth for initial signup and
  login, with email signup gated on suitable SMTP.
  [Supabase pricing](https://supabase.com/pricing) ·
  [Terms](https://supabase.com/terms) ·
  [Auth email limits](https://supabase.com/docs/guides/auth/auth-smtp)
- Cloudflare Workers AI Free has a daily 10,000-neuron allowance that
  fails closed on the free plan. Its BGE Small candidate emits
  384-dimensional vectors, incompatible with current Jina indexes.
  Treat it as a candidate pending account eligibility and endpoint
  verification. A later opt-in implementation would build a separate
  index keyed by model, revision, dimensions and encoding policy, and
  reject mismatched queries. Gemini is unsuitable for a general beta
  because its terms require API users to be 18 or older, restrict apps
  likely to be accessed by minors, and constrain free use by region.
  No hosted generation provider is approved. Keep generation disabled
  pending eligibility, privacy and hard-budget verification.
  [Workers AI pricing](https://developers.cloudflare.com/workers-ai/platform/pricing/) ·
  [BGE Small](https://developers.cloudflare.com/workers-ai/models/bge-small-en-v1.5/) ·
  [Gemini terms](https://ai.google.dev/gemini-api/terms)

No account or project was created. Platform eligibility, project quotas
and billing settings remain to be confirmed by an eligible operator.

## Database and deployment decision

The local schema is at `0004_vector_retrieval` and the isolated database
passed `alembic check`. For Supabase, prefer the IPv4 session pooler on
5432 with certificate and hostname verification. Use an explicitly
bounded application pool (start at 2 connections with no overflow) and
a separate migration role on a direct connection if IPv6 is available,
or the session pooler otherwise. Transaction pooling on 6543 lacks
prepared statement support and is unsuitable for the current asyncpg /
SQLAlchemy defaults. On a disposable hosted project, verify the actual
certificate chain, schema/search path (the hosted extension can be in
`extensions`), privileges, extension visibility, fresh upgrade, drift,
and a real vector round-trip before promotion. Disable direct browser
access to application tables through the Data API. No hosted migration
or pool connection has been tested.
[Supabase connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres) ·
[TLS enforcement](https://supabase.com/docs/guides/platform/ssl-enforcement) ·
[pgvector](https://supabase.com/docs/guides/database/extensions/pgvector)

Prefer a Render Static Site and a single FastAPI instance, with HTTPS,
an exact frontend-origin allowlist, and a migration gate before rollout.
Keep GitHub ingestion initiated by an authenticated, quota-checked
workspace and initially restrict invites and ingest concurrency. Prefer
prepared snapshots if graph/chunk builds are too slow at 0.1 CPU.

## Approval gates

1. Approve Phase 2 local implementation. Add verified Supabase JWT
   identities, tenant-scoped grants and deletion. Preserve existing data
   under an operator-only workspace until explicitly shared.
2. Test access denial across every tenant resource and concurrent
   persistent limits before enabling ingestion. Use global capacity
   and byte limits in addition to per-user file and repository counts.
3. Confirm eligible operator-owned free accounts before a disposable
   hosted smoke test. Inspect billing settings, verify TLS/session
   pooling and run migrations before traffic. Repeat cold-start and
   ingestion measurements before selecting Render as the launch host.
4. Prepare the SaaS UI and deployment configuration in their respective
   phases. Verify backup/restore and abuse controls before requesting
   separate public launch approval. Leave unverified AI features disabled.
