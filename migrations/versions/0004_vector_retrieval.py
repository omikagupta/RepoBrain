"""Add atomic, snapshot-scoped vector indexes."""

import sqlalchemy as sa
from alembic import op
from pgvector.sqlalchemy import VECTOR

revision = "0004_vector_retrieval"
down_revision = "0003_lexical_retrieval"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_unique_constraint(
        "uq_source_chunks_version_id",
        "source_chunks",
        ["snapshot_id", "chunking_version", "id"],
    )
    op.create_table(
        "vector_indexes",
        sa.Column("snapshot_id", sa.Uuid(), primary_key=True),
        sa.Column("chunking_version", sa.String(24), nullable=False),
        sa.Column("vector_version", sa.String(24), nullable=False),
        sa.Column("model_id", sa.Text(), nullable=False),
        sa.Column("model_revision", sa.Text(), nullable=False),
        sa.Column("dimension", sa.Integer(), nullable=False),
        sa.Column("encoding_policy", sa.Text(), nullable=False),
        sa.Column("chunk_count", sa.Integer(), nullable=False),
        sa.Column(
            "completed_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "snapshot_id",
            "chunking_version",
            "vector_version",
            name="uq_vector_indexes_version",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "chunking_version"],
            ["search_indexes.snapshot_id", "search_indexes.chunking_version"],
            name="fk_vector_indexes_lexical_index",
            ondelete="CASCADE",
        ),
        sa.CheckConstraint("dimension = 768", name="ck_vector_indexes_dimension"),
    )
    op.create_table(
        "chunk_embeddings",
        sa.Column("chunk_id", sa.Uuid(), primary_key=True),
        sa.Column("snapshot_id", sa.Uuid(), nullable=False),
        sa.Column("chunking_version", sa.String(24), nullable=False),
        sa.Column("vector_version", sa.String(24), nullable=False),
        sa.Column("embedding", VECTOR(768), nullable=False),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "chunking_version", "vector_version"],
            [
                "vector_indexes.snapshot_id",
                "vector_indexes.chunking_version",
                "vector_indexes.vector_version",
            ],
            name="fk_chunk_embeddings_vector_index",
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["snapshot_id", "chunking_version", "chunk_id"],
            [
                "source_chunks.snapshot_id",
                "source_chunks.chunking_version",
                "source_chunks.id",
            ],
            name="fk_chunk_embeddings_source_chunk",
        ),
    )
    op.create_index(
        "ix_chunk_embeddings_snapshot_version",
        "chunk_embeddings",
        ["snapshot_id", "vector_version"],
    )


def downgrade() -> None:
    raise RuntimeError("Vector retrieval migration is forward-only")
