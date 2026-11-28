# Staging readiness review

**Decision.** The package can be reviewed locally. Public staging is blocked.
The Render Free web service has public ingress. Auto-deploy off controls
subsequent Git pushes and is not an access control or a guarantee that
initial Blueprint creation is inert. The public configuration requires an
eligible operator and separate approval.

| Requirement | Status | Evidence |
| --- | --- | --- |
| Render Blueprint fields and paths | PASS | Validated against Render's public JSON Schema using check-jsonschema. Reviewed runtime, paths and headers against the official reference. |
| Render account/workspace validation and first sync | UNVERIFIED | No account, authorized workspace, sync or resource creation in this review. Dashboard secret-file upload and hostname selection are manual. |
| Private staging using only the expected Free services | FAIL | Render Free web ingress is public. Auto-deploy and CORS do not restrict network reachability. Free cannot use Blueprint IP allowlists or paid maintenance mode. |
| Fail-closed configuration | PASS | Startup tests refuse local mode and missing database URL, CA, issuer or frontend origin. Schema readiness rejects unavailable or incompatible databases. Errors redact the URL. |
| PostgreSQL TLS settings | PASS | The connection factory passes an SSL context requiring certificate and hostname checks. The engine pool caps connections at two with no overflow. |
| Live Supavisor TLS, prepared statements, and application role | UNVERIFIED | Port 5432 session mode supports prepared statements in provider documentation. No live certificate chain, round-trip, search path, or role grants were tested. |
| Migration and extension readiness | PASS | The disposable PostgreSQL suite upgrades the schema, checks Alembic drift and exercises readiness. The hosted launcher runs no migrations. |
| Operator migration/rollback against Supabase | UNVERIFIED | Free has no pre-deploy hook. A separately authorized operator must test the migration role, application grants, extension visibility, and forward recovery. |
| Production frontend build and origin constraints | PASS | Offline hosted build emits a CSP with the exact HTTPS API/Auth origins. Build validation requires a publishable key. The backend tests exact-origin CORS and rejects lookalike origins. |
| Live browser headers, redirects and email verification | UNVERIFIED | Static Blueprint config sets nosniff, referrer policy and DENY framing. Live CDN rewrite behavior and a verified email callback require an eligible operator and approved SMTP. |
| Hosted authentication, isolation, quotas and deletion | PASS | The two-user integration checklist uses signed JWTs, mocked GitHub traffic and disposable PostgreSQL. It covers expiry, workspace creation, pinned ingestion, readiness, lexical search, graph and source, quota Retry-After, and removal of access. |
| App-level abuse bounds | PASS | Existing tests cover bounded request/response streaming, admission, body deadlines, persistent quota races and deletion fencing. |
| Required app-specific edge controls on Free | FAIL | Render provides generic DDoS protection and inbound throttling. No equivalent Free policy was verified for app-specific per-peer limits, route budgets, or private ingress. |
| Backup procedure and recovery prerequisites | PASS | See the scoped backup and restore drill below. Free has no automatic backup or PITR. |
| Supabase restore, Auth continuity, and hosted rollback drill | UNVERIFIED | No provider project or archive was used. A restore into an isolated target and verification of user UUID mapping and role grants remain prerequisites. |
| Frozen benchmark and local retrieval | PASS | Benchmark audit verifies all 800 records; no retrieval algorithm, benchmark artifact, or measured result changed. |
| Zero-cost policy and hosted AI | PASS | The package selects Free and leaves hosted AI and automatic index preparation disabled. No accounts, resources or payment were used. |
| Actual zero-cost staging and cold-start availability | UNVERIFIED | Requires provider eligibility, billing checks and authorized live testing. Local timing is recorded separately. |

[Render Blueprint reference](https://render.com/docs/blueprint-spec) ·
[Render Free limits](https://render.com/docs/free) ·
[Render inbound throttling](https://render.com/docs/troubleshooting-deploys) ·
[Supabase connection modes](https://supabase.com/docs/guides/database/connecting-to-postgres) ·
[Supabase SSL enforcement](https://supabase.com/docs/guides/platform/ssl-enforcement)

## Migration and backup review

Use the session pooler hostname from the project dashboard as the TLS
verification name. Keep default asyncpg prepared statements for session
pooling. Hostname or chain errors are blockers. Test `current_user`,
`current_schemas(true)`, `to_regtype('vector')`, a prepared query and
transactional app CRUD with the actual app role before traffic. The
app role needs schema and extension usage plus DML on app tables. It
should have SELECT-only access to `alembic_version`; it does not need
owner, DDL, Auth administration, or Data API permissions. Verify that
the role cannot create or drop tables. Keep rights to enable or use the
managed extension and migrate with the separately authorized migration
role. Never run schema downgrades as deployment rollback.

Scope the plain PostgreSQL archive to the RepoBrain schema and keep it in
encrypted operator storage. Manage grants and required extensions separately.
An application-only backup does not restore Supabase Auth identities.
Workspace ownership is keyed to the original JWT subject UUIDs. A restore
with new UUIDs requires a reviewed identity mapping before access is enabled.
For authorized platform-to-platform migration, follow the Supabase-specific
procedure, including roles and held data, and independently preserve Auth
configuration, SMTP, redirect allowlists, signing-key management and any
Storage objects. Verify which Auth rows can transfer and use a fresh
session to test sign-in. A verified archive listing alone is not a restore.
Free has no automatic backup or point-in-time recovery.

[Supabase Free pricing](https://supabase.com/pricing) ·
[Supabase backup and restore procedure](https://supabase.com/docs/guides/platform/migrating-within-supabase/backup-restore)
