"""Enable pgvector and add repository persistence."""

import sqlalchemy as sa
from alembic import op

revision = "0001_database_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")
    op.create_table(
        "repositories",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column("owner", sa.Text(), nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.UniqueConstraint("owner", "name", name="uq_repositories_owner_name"),
        sa.CheckConstraint("owner ~ '^[a-z0-9_-]+$'", name="ck_repositories_owner"),
        sa.CheckConstraint("name ~ '^[a-z0-9_.-]+$'", name="ck_repositories_name"),
    )
    op.create_table(
        "repository_snapshots",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "repository_id",
            sa.Uuid(),
            sa.ForeignKey("repositories.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("commit_sha", sa.String(40), nullable=False),
        sa.Column(
            "ingestion_state", sa.String(9), server_default="pending", nullable=False
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "repository_id", "commit_sha", name="uq_snapshots_repository_commit"
        ),
        sa.CheckConstraint(
            "commit_sha ~ '^[0-9a-f]{40}$'", name="ck_snapshots_commit_sha"
        ),
        sa.CheckConstraint(
            "ingestion_state IN ('pending', 'running', 'completed', 'failed')",
            name="ck_snapshots_ingestion_state",
        ),
    )
    op.execute("""
        CREATE FUNCTION repobrain_update_snapshot() RETURNS trigger
        LANGUAGE plpgsql AS $$
        BEGIN
            IF NEW.repository_id IS DISTINCT FROM OLD.repository_id
               OR NEW.commit_sha IS DISTINCT FROM OLD.commit_sha THEN
                RAISE EXCEPTION 'snapshot repository and commit are immutable'
                    USING ERRCODE = '23514';
            END IF;
            NEW.updated_at := statement_timestamp();
            RETURN NEW;
        END;
        $$;
    """)
    op.execute("""
        CREATE TRIGGER update_snapshot
        BEFORE UPDATE ON repository_snapshots
        FOR EACH ROW EXECUTE FUNCTION repobrain_update_snapshot();
    """)
    op.create_table(
        "source_files",
        sa.Column("id", sa.Uuid(), primary_key=True),
        sa.Column(
            "snapshot_id",
            sa.Uuid(),
            sa.ForeignKey("repository_snapshots.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("path", sa.Text(), nullable=False),
        sa.Column("content_sha256", sa.String(64), nullable=False),
        sa.Column("language", sa.Text(), nullable=False),
        sa.Column("line_count", sa.Integer(), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.UniqueConstraint(
            "snapshot_id", "path", name="uq_source_files_snapshot_path"
        ),
        sa.CheckConstraint(
            "path <> '' AND path !~ '(^/|/$|//|(^|/)[.]{1,2}(/|$)|^[A-Za-z]:)' "
            "AND strpos(path, chr(92)) = 0",
            name="ck_source_files_relative_path",
        ),
        sa.CheckConstraint(
            "content_sha256 ~ '^[0-9a-f]{64}$'", name="ck_source_files_sha256"
        ),
        sa.CheckConstraint("btrim(language) <> ''", name="ck_source_files_language"),
        sa.CheckConstraint("line_count >= 0", name="ck_source_files_line_count"),
    )


def downgrade() -> None:
    op.drop_table("source_files")
    op.drop_table("repository_snapshots")
    op.execute("DROP FUNCTION repobrain_update_snapshot()")
    # Preserve vector because it may predate this migration or have other users.
    op.drop_table("repositories")
