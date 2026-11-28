"""Add workspace ownership without changing existing public snapshots."""

import sqlalchemy as sa
from alembic import op

revision = "0005_workspace_ownership"
down_revision = "0004_vector_retrieval"


def upgrade() -> None:
    op.create_table(
        "saas_users",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    op.create_table(
        "workspaces",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "owner_id", sa.Uuid(), sa.ForeignKey("saas_users.id"), nullable=False
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.UniqueConstraint("owner_id"),
    )
    op.create_table(
        "workspace_snapshots",
        sa.Column(
            "workspace_id",
            sa.Uuid(),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("repository_snapshots.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.create_index(
        "ix_workspace_snapshots_snapshot_id", "workspace_snapshots", ["snapshot_id"]
    )


def downgrade() -> None:
    raise RuntimeError("Workspace ownership migration is forward-only")
