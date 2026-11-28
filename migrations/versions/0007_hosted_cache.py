"""Track only new hosted snapshots for bounded cache retention."""

import sqlalchemy as sa
from alembic import op

revision = "0007_hosted_cache"
down_revision = "0006_hosted_quotas"


def upgrade() -> None:
    op.create_table(
        "hosted_cache_entries",
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("repository_snapshots.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("reserved_bytes", sa.Integer(), nullable=False),
        sa.Column("touched_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_hosted_cache_entries_touched_at", "hosted_cache_entries", ["touched_at"]
    )


def downgrade() -> None:
    raise RuntimeError("Hosted cache migration is forward-only")
