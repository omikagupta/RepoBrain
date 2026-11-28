"""Add persistent hosted usage counters and expiring ingestion leases."""

import sqlalchemy as sa
from alembic import op

revision = "0006_hosted_quotas"
down_revision = "0005_workspace_ownership"


def upgrade() -> None:
    op.create_table(
        "usage_windows",
        sa.Column("owner_id", sa.Uuid(), primary_key=True),
        sa.Column("kind", sa.String(24), primary_key=True),
        sa.Column("window_start", sa.DateTime(timezone=True), nullable=False),
        sa.Column("count", sa.Integer(), nullable=False),
    )
    op.create_table(
        "ingestion_leases",
        sa.Column("owner_id", sa.Uuid(), primary_key=True),
        sa.Column("token", sa.Uuid(), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    raise RuntimeError("Hosted quotas migration is forward-only")
