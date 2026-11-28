# Hosted identity and workspace isolation

The default `REPOBRAIN_DEPLOYMENT_MODE=local` keeps the single-operator
workflow and all retrieval modes. Keep this mode on loopback or on the
trusted network described in the private deployment guide. It does not
authenticate callers.

For hosted-mode testing set `REPOBRAIN_DEPLOYMENT_MODE=hosted`,
`REPOBRAIN_DATABASE_URL`, and `REPOBRAIN_AUTH_ISSUER` (trusted HTTPS
origin plus `/auth/v1`, or plain HTTP on literal loopback for local Supabase).
The audience defaults to `authenticated`. Use asymmetric ES256 or RS256
signing keys. The backend verifies key ID, algorithm, signature, issuer,
audience, expiry, authenticated role and UUID subject. It caches trusted
JWKS for 60 seconds, refreshes on an unknown key after a short cooldown
and fails closed when expired keys cannot be refreshed. No identity
requests are made at boot.

Set `VITE_DEPLOYMENT_MODE=hosted`, `VITE_SUPABASE_URL` and
`VITE_SUPABASE_PUBLISHABLE_KEY` for the frontend. The publishable key is
public by design. Use the frontend dev proxy or same-origin reverse proxy.
Keep the signing keys, database URL, service role and provider credentials
on the server. The frontend supports email/password registration and sign-in
through Supabase Auth. For local testing, use a local Supabase project with
asymmetric keys or run the automated tests with ephemeral signing keys.
General-user email confirmation remains gated on suitable SMTP in any
future hosted project. Enable email verification with signup.

## Ownership and retention

A verified identity explicitly creates its workspace from the dashboard.
A successful hosted ingestion submission grants that workspace access to
the pinned public snapshot. Knowing a snapshot UUID provides no access.
Status, graph, nodes, edges, neighborhood, source, readiness, all search
modes and answers require a grant before their respective handler runs.
Hosted mode does not instantiate an ONNX provider and disables vector,
hybrid, graph-enhanced retrieval and answers.

Workspaces share immutable public snapshot content and derived indexes.
Workspace membership, effective ownership and account state remain private.
Deleting a repository removes that workspace's grants for all its commits.
Deleting a workspace removes its grants. Closing a RepoBrain account also
retains only a UUID tombstone and deletion timestamp to prevent a still-valid
identity token from recreating the account. Identity-provider deletion is
separate and requires its own administrative process. Public source
snapshots and derived artifacts remain cached after grant removal, including
when no workspace references them. No physical pruning is performed here.
Existing snapshots are preserved by migration and start with no hosted
grants.

Workspace mutations and ingestion grant creation lock the workspace row.
Removal fences a submission already resolving a GitHub reference so it
cannot restore a deleted grant. An ingestion that already granted access
can still finish producing shared public content after deletion. Reads that
passed authorization before removal can finish; subsequent requests
recheck ownership. Closing an account prevents workspace reprovisioning
even while the issuer's token remains valid.

## Verification and limits

Run `docker compose -f compose.test.yaml up --build --abort-on-container-exit
--exit-code-from tests` from the repository root. The integration suite
requires a fresh disposable database and checks Alembic drift. The
`0005_workspace_ownership` migration is forward-only. Deploy a previous
application revision only on a private, isolated system after verifying
schema compatibility. The previous application does not enforce tenancy.
Use the migration safety and backup rules before production rollout.

The hosted profile is a security boundary for local validation. Repository
analysis and lexical index building still use the existing operator CLI.
Do not expose ingestion publicly before persistent quotas and abuse limits
are in place. Cloud account eligibility, production SMTP, hosted TLS,
pooling, backup/restore, and deployment verification are pending.
