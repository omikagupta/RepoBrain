# RepoBrain zero-cost deployment runbook

See the [staging readiness matrix](saas-staging-review.md) for local
evidence, failed launch requirements, and unverified provider checks.

This package is for an eligible operator after separate deployment and
security approval. The local checks use disposable PostgreSQL, generated
JWT signing keys, fake GitHub responses, and no cloud credentials.
Use local development if you cannot independently meet a provider's
terms. Never misstate eligibility or share another person's credentials.

## 1. Confirm the free-tier boundaries

- Render Free Web Service has 0.1 CPU, 512 MB and 750 instance hours per
  workspace each month. It sleeps after 15 idle minutes. A Static Site
  adds no compute service but shares bandwidth and build quotas. Keep the
  workspace on Hobby without a payment method and accept suspension or
  paused builds. Render prohibits use under 16 and requires capacity to
  enter a binding contract. Check both eligibility and the billing
  dashboard before proceeding.
  [Limits](https://render.com/docs/free) · [Compute](https://render.com/docs/compute-plans) ·
  [Terms](https://render.com/terms)
- Supabase Free currently includes 500 MB of database storage, 5 GB egress
  and a pause after one week of inactivity. Free has no automatic backups.
  The operator must be authorized to accept its binding terms.
  [Pricing](https://supabase.com/pricing) · [Terms](https://supabase.com/terms)
- Render managed HTTPS is suitable for transport encryption and its DDoS
  protection is an additional layer. This package relies on RepoBrain's
  limits for admission and quotas. No equivalent configurable edge
  per-client policy has been verified on Free. The application gate runs
  after traffic has reached the service and can be exhausted. Keep this
  a public-launch blocker until the threat model and edge controls are
  separately approved. Do not add a second Nginx service.
  [Render static sites and DDoS protection](https://render.com/docs/static-sites)

## 2. Configure the eligible operator's Supabase project

1. Use Free and choose a region close to the API. Keep the database
   credentials server-side. Disable the Data API for application tables
   unless an independently reviewed restricted schema is needed.
2. Enable pgvector and enforce database TLS. In **Connect**, select
   **Session pooler**, port **5432**, for IPv4. Download the appropriate
   CA for the selected hostname and verify the certificate chain against
   that endpoint. Use full certificate and hostname verification. Do
   not use transaction pooling (6543). It does not support the prepared
   statements used by SQLAlchemy/asyncpg.
3. Provision a dedicated least-privilege application role with application
   DML and schema/extension usage only. Keep DDL in a separate migration
   role. Validate the role-specific session-pooler usernames with the
   dashboard and confirm the search path resolves `vector` (often in
   `extensions`) as well as application tables. Configure the role on
   the database and verify it with a real round-trip. Do not add URL
   options when using the app's verified-TLS setting.
4. In Auth, use an asymmetric ES256 or RS256 signing key and issuer
   `https://PROJECT.supabase.co/auth/v1`. The expected audience is
   `authenticated`. Enable verified email signup. Set Site URL to the
   final frontend HTTPS URL and allow exactly its `/login` callback.
   The default SMTP only delivers to team addresses and is unsuitable
   for public signup. Use an eligible, reviewed zero-cost SMTP service
   or keep signup restricted. Do not enable unverified signup to work
   around SMTP restrictions.
   [Connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres) ·
   [SSL](https://supabase.com/docs/guides/platform/ssl-enforcement) ·
   [Signing keys](https://supabase.com/docs/guides/auth/signing-keys) ·
   [SMTP](https://supabase.com/docs/guides/auth/auth-smtp)

## 3. Back up and migrate before starting Render

Freeze writes for a consistent cutover. Use PostgreSQL client binaries
compatible with the server. Configure an untracked pgpass file with
restricted permissions and take an encrypted backup outside the checkout.
The commands below expect a preconfigured pgpass path, operator
environment, and a migration-role URL supplied by a secret store.

```powershell
$env:PGSSLMODE = 'verify-full'
$env:PGSSLROOTCERT = $env:REPOBRAIN_OPERATOR_CA_PATH
$env:PGPASSFILE = $env:REPOBRAIN_OPERATOR_PGPASS_PATH
pg_dump --dbname 'service=repobrain-backup' --schema public --format custom --file $env:REPOBRAIN_BACKUP_PATH
if ($LASTEXITCODE) { throw 'Backup failed' }
pg_restore --list $env:REPOBRAIN_BACKUP_PATH
if ($LASTEXITCODE) { throw 'Backup archive cannot be read' }

$env:REPOBRAIN_DEPLOYMENT_MODE = 'hosted'
$env:REPOBRAIN_AUTH_ISSUER = 'https://PROJECT.supabase.co/auth/v1'
$env:REPOBRAIN_DATABASE_TLS_CA = $env:REPOBRAIN_OPERATOR_CA_PATH
$env:REPOBRAIN_DATABASE_URL = $env:REPOBRAIN_MIGRATION_DATABASE_URL
uv run --locked alembic upgrade head
if ($LASTEXITCODE) { throw 'Migration failed. Do not deploy.' }
uv run --locked alembic check
if ($LASTEXITCODE) { throw 'Schema drift detected. Do not deploy.' }
Remove-Item Env:REPOBRAIN_DATABASE_URL
```

Configure the libpq service entry separately with the session pooler
host, port 5432, password-free connection metadata and the appropriate
role. Verify the restore into a separate isolated database with
`pg_restore --exit-on-error --no-owner --no-privileges --dbname
'service=repobrain-restore' BACKUP_PATH`, then verify extensions, schema
head, ownership constraints and application read/write behavior. The
PostgreSQL archive is not a complete backup of Supabase Auth settings,
signing keys, or providers. Back up those settings and plan for identity
recovery separately. Use a disposable project for provider restore
verification. Never test a destructive restore on a live database.

On migration failure, stop and diagnose from protected logs. Do not
retry blindly or run downgrades. Keep the old compatible hosted release
or suspend service until a forward fix. If rollback is required after
release, use a previously verified hosted build with schema compatibility,
or restore to an isolated instance after explicit operator approval and
verification. Never roll back to an unauthenticated backend.

## 4. Configure Render without enabling public traffic

The reviewed definitions are in `render.yaml`. If the Blueprint cannot
stage resources without immediately exposing endpoints, keep it unapplied
until deployment and traffic exposure are explicitly approved. Record the
final service URLs first so the origin settings can be exact. Disable
auto-deploy. Render Free does not support the paid pre-deploy command;
only the operator runs migrations.

| Dashboard field | Value |
| --- | --- |
| Backend | Docker Web Service, Free, repository root, `./Dockerfile` |
| Docker Command | `python -m repobrain.hosted` |
| Managed health path | `/readyz` |
| Backend secret file | `supabase-ca.pem` at `/etc/secrets/supabase-ca.pem` |
| Backend database URL | Verified-TLS session pooler endpoint using the application role |
| Backend auth and origin | `REPOBRAIN_AUTH_ISSUER`, `REPOBRAIN_HOSTED_FRONTEND_ORIGIN` |
| Static site | Root `frontend`, build `npm ci && npm run build:hosted`, publish `dist` |
| Static SPA route | Rewrite `/*` to `/index.html` |
| Public frontend config | `VITE_DEPLOYMENT_MODE=hosted`, API origin, Supabase origin and publishable key from the Blueprint |

The backend reads Render's injected `PORT`, refuses the local profile,
checks the current migrated schema and pgvector before serving, and
uses at most two pooled connections without overflow. Keep separate
process health at `/healthz`. Permit only the exact frontend HTTPS
origin in CORS and public Auth redirects. Copy no DB, signing,
Supabase service-role, GitHub or model credentials into Vite variables.
Keep hosted managed indexing and AI off; prepared snapshots are the
fallback. Verify the static site's headers and install an exact
build-specific Content-Security-Policy permitting only the configured
Auth/API origins before public launch. The hosted build includes this
policy in its HTML; verify it in the delivered document along with
Blueprint response headers. If an HTTP CSP is also configured, keep both
policies compatible. The Blueprint was validated with the public schema,
independent of an account. This does not validate workspace names,
domain configuration or first-sync behavior.

## 5. Local verification and later launch gates

Run the full backend, PostgreSQL, frontend build and browser CI. The
hosted PostgreSQL tests exercise JWT signing, workspace creation, quota
admission, cancelled ingestion and indexing, re-submission, isolation
and deletion. The offline runtime probe uses the real ingestion, graph
and lexical builders, mocked upstreams and the non-root image. It does
not validate TLS, Supavisor or a real Render control plane.

The local Phase 4 probe used 0.1 CPU, 512 MiB, 40 real Python files
(210,721 bytes) and an injected 80 ms delay per GitHub request. The
cached image build took 17.645 seconds and produced a 266,937,758-byte
image. The probe reached ASGI health in 32.300 seconds, then completed
ingestion and both index builds in 39.297 seconds. A six-request mixed
graph and lexical burst returned six HTTP 200 responses in 1.798
seconds. Two PostgreSQL connections were observed after the burst.
Peak backend cgroup memory was 105,115,648 bytes, with 9.944 CPU seconds
for the full probe. The startup figure is an in-container ASGI probe,
without provider wake-up or TLS. Keep managed preparation off by default.

Reproduce from the repository root on Docker Desktop. The database URL
below is the disposable Compose fixture. The probe enables preparation
only within its own container.

```powershell
$project = 'repobrain-phase4-probe'
docker compose -p $project -f compose.test.yaml run --build --rm runtime-graph-smoke
if ($LASTEXITCODE) { throw 'Migration or runtime smoke failed' }
docker run --rm --network "${project}_default" --cpus .1 --memory 512m --memory-swap 512m `
  -e REPOBRAIN_DEPLOYMENT_MODE=hosted `
  -e REPOBRAIN_AUTH_ISSUER=https://identity.example.invalid/auth/v1 `
  -e REPOBRAIN_HOSTED_PREPARE_INDEXES=true -e REPOBRAIN_PROBE_FILES=40 `
  -e REPOBRAIN_PROBE_LATENCY_MS=80 `
  -e REPOBRAIN_DATABASE_URL=postgresql+asyncpg://repobrain_test:repobrain-test-only@test-db:5432/repobrain_test `
  -v "${PWD}/src/repobrain:/sample:ro" -v "${PWD}/tests/hosted_runtime_probe.py:/probe.py:ro" `
  "${project}-runtime-graph-smoke" python /probe.py
if ($LASTEXITCODE) { throw 'Offline workload probe failed' }
docker compose -p $project -f compose.test.yaml down
```

After a distinct deployment approval, verify hosted TLS, database role
permissions, verified email delivery, login and session expiry, CORS,
two-account isolation, cold start and live latency using an authorized
staging setup. Check readiness after migration, test restore and
confirmed rollback, and audit the billing dashboard, edge abuse policy,
source-cache capacity and retention before any public traffic.
