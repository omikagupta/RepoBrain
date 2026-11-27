"""Add snapshot-scoped Python code graphs."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import JSONB

revision = "0002_python_code_graph"
down_revision = "0001_database_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_source_files_snapshot_id", "source_files", ["snapshot_id", "id"]
    )
    op.create_table(
        "graph_analyses",
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("repository_snapshots.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("analyzed_files", sa.Integer(), nullable=False),
        sa.Column("node_count", sa.Integer(), nullable=False),
        sa.Column("edge_count", sa.Integer(), nullable=False),
        sa.Column("diagnostics", JSONB(), nullable=False),
    )
    op.create_table(
        "graph_nodes",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("graph_analyses.snapshot_id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("source_file_id", sa.Uuid(), nullable=False),
        sa.Column("stable_key", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(24), nullable=False),
        sa.Column("qualified_name", sa.Text(), nullable=False),
        sa.Column("start_line", sa.Integer()),
        sa.Column("end_line", sa.Integer()),
        sa.Column("is_async", sa.Boolean(), nullable=False),
        sa.UniqueConstraint("snapshot_id", "id", name="uq_graph_nodes_snapshot_id"),
        sa.UniqueConstraint(
            "snapshot_id", "stable_key", name="uq_graph_nodes_snapshot_key"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "source_file_id"],
            ["source_files.snapshot_id", "source_files.id"],
            name="fk_graph_nodes_source_file",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_graph_nodes_snapshot_file", "graph_nodes", ["snapshot_id", "source_file_id"]
    )
    op.create_table(
        "graph_edges",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("source_id", sa.Uuid(), nullable=False),
        sa.Column("target_id", sa.Uuid(), nullable=False),
        sa.Column("stable_key", sa.String(64), nullable=False),
        sa.Column("relationship", sa.String(24), nullable=False),
        sa.Column("line", sa.Integer()),
        sa.Column("column", sa.Integer()),
        sa.Column("provenance", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "snapshot_id", "stable_key", name="uq_graph_edges_snapshot_key"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "source_id"],
            ["graph_nodes.snapshot_id", "graph_nodes.id"],
            name="fk_graph_edges_source_node",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "target_id"],
            ["graph_nodes.snapshot_id", "graph_nodes.id"],
            name="fk_graph_edges_target_node",
            ondelete="CASCADE",
        ),
    )
    op.create_index(
        "ix_graph_edges_snapshot_source", "graph_edges", ["snapshot_id", "source_id"]
    )
    op.create_index(
        "ix_graph_edges_snapshot_target", "graph_edges", ["snapshot_id", "target_id"]
    )


def downgrade() -> None:
    raise RuntimeError("Graph migration is forward-only")
