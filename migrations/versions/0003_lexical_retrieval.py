"""Add versioned source chunks and lexical search indexes."""

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import TSVECTOR

revision = "0003_lexical_retrieval"
down_revision = "0002_python_code_graph"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "search_indexes",
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("repository_snapshots.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("chunking_version", sa.String(24), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column("indexed_files", sa.Integer(), nullable=False),
        sa.Column("indexed_bytes", sa.Integer(), nullable=False),
        sa.Column(
            "built_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "snapshot_id", "chunking_version", name="uq_search_index_version"
        ),
    )
    op.create_table(
        "source_chunks",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("chunking_version", sa.String(24), nullable=False),
        sa.Column("source_file_id", sa.Uuid(), nullable=False),
        sa.Column("stable_key", sa.String(64), nullable=False),
        sa.Column("start_line", sa.Integer(), nullable=False),
        sa.Column("end_line", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("source_sha256", sa.String(64), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("token_text", sa.Text(), nullable=False),
        sa.Column(
            "search_vector",
            TSVECTOR(),
            sa.Computed("to_tsvector('simple'::regconfig, token_text)", persisted=True),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "snapshot_id", "stable_key", name="uq_source_chunks_snapshot_key"
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "chunking_version"],
            ["search_indexes.snapshot_id", "search_indexes.chunking_version"],
            name="fk_source_chunks_search_index",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "source_file_id"],
            ["source_files.snapshot_id", "source_files.id"],
            name="fk_source_chunks_source_file",
        ),
        sa.CheckConstraint(
            "start_line >= 1 AND end_line >= start_line", name="ck_source_chunks_range"
        ),
    )
    op.create_index(
        "ix_source_chunks_snapshot_file",
        "source_chunks",
        ["snapshot_id", "source_file_id", "start_line"],
    )
    op.create_index(
        "ix_source_chunks_search_vector",
        "source_chunks",
        ["search_vector"],
        postgresql_using="gin",
    )


def downgrade() -> None:
    raise RuntimeError("Lexical search migration is forward-only")
