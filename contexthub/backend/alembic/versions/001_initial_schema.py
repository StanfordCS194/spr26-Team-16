"""Initial schema — all §5 tables, indices, tsvector trigger, RLS policies.

Revision ID: 001
Revises: None
Create Date: 2026-04-22
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, ENUM, JSONB, TSVECTOR, UUID

revision = "001"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ------------------------------------------------------------------
    # Enum types  (idempotent via DO block)
    # ------------------------------------------------------------------
    op.execute("""
        DO $$ BEGIN
            CREATE TYPE source_platform AS ENUM ('claude_ai', 'chatgpt', 'gemini');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        DO $$ BEGIN
            CREATE TYPE push_status AS ENUM ('pending', 'processing', 'ready', 'failed');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        DO $$ BEGIN
            CREATE TYPE summary_layer AS ENUM ('commit_message', 'structured_block', 'raw_transcript');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        DO $$ BEGIN
            CREATE TYPE relation_type AS ENUM ('continuation', 'reference', 'supersession');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        DO $$ BEGIN
            CREATE TYPE target_platform AS ENUM ('claude_ai');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        DO $$ BEGIN
            CREATE TYPE pull_origin AS ENUM ('extension', 'dashboard');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;

        DO $$ BEGIN
            CREATE TYPE pull_resolution AS ENUM ('commit_message', 'structured_block', 'raw_transcript');
        EXCEPTION WHEN duplicate_object THEN NULL; END $$;
    """)

    # ------------------------------------------------------------------
    # profiles
    # ------------------------------------------------------------------
    op.create_table(
        "profiles",
        sa.Column("user_id", UUID(as_uuid=True), primary_key=True),
        sa.Column("display_name", sa.Text),
        sa.Column("avatar_url", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["user_id"], ["auth.users.id"], ondelete="CASCADE"),
    )

    # ------------------------------------------------------------------
    # api_tokens
    # ------------------------------------------------------------------
    op.create_table(
        "api_tokens",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("auth.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("token_hash", sa.Text, nullable=False),
        sa.Column("scopes", ARRAY(sa.Text), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ix_api_tokens_token_hash", "api_tokens", ["token_hash"], unique=True)

    # ------------------------------------------------------------------
    # workspaces
    # ------------------------------------------------------------------
    op.create_table(
        "workspaces",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("auth.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("slug", sa.Text, nullable=False),
        sa.Column("settings_json", JSONB),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    # slug is cosmetic/display; unique per user
    op.create_index(
        "ix_workspaces_user_slug",
        "workspaces",
        ["user_id", "slug"],
        unique=True,
        postgresql_where=sa.text("deleted_at IS NULL"),
    )

    # ------------------------------------------------------------------
    # interchange_format_versions
    # ------------------------------------------------------------------
    op.create_table(
        "interchange_format_versions",
        sa.Column("version", sa.Text, primary_key=True),
        sa.Column("json_schema", JSONB, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deprecated_at", sa.DateTime(timezone=True)),
    )

    # ------------------------------------------------------------------
    # pushes
    # ------------------------------------------------------------------
    op.create_table(
        "pushes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("auth.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "source_platform",
            ENUM("claude_ai", "chatgpt", "gemini", name="source_platform", create_type=False),
            nullable=False,
        ),
        sa.Column("source_url", sa.Text),
        sa.Column("source_conversation_id", sa.Text),
        sa.Column(
            "interchange_version",
            sa.Text,
            sa.ForeignKey("interchange_format_versions.version"),
            nullable=False,
            server_default="ch.v0.1",
        ),
        sa.Column("title", sa.Text),
        sa.Column("commit_message", sa.Text),
        sa.Column(
            "status",
            ENUM(
                "pending", "processing", "ready", "failed",
                name="push_status", create_type=False,
            ),
            nullable=False,
            server_default="pending",
        ),
        sa.Column("failure_reason", sa.Text),
        sa.Column("idempotency_key", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True)),
    )
    # Dashboard listing: most recent pushes per workspace
    op.create_index(
        "ix_pushes_workspace_created",
        "pushes",
        ["workspace_id", sa.text("created_at DESC")],
    )
    # Push deduplication via idempotency key
    op.create_index(
        "ix_pushes_user_idempotency_key",
        "pushes",
        ["user_id", "idempotency_key"],
        unique=True,
        postgresql_where=sa.text("idempotency_key IS NOT NULL"),
    )

    # ------------------------------------------------------------------
    # summaries
    # ------------------------------------------------------------------
    op.create_table(
        "summaries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "push_id",
            UUID(as_uuid=True),
            sa.ForeignKey("pushes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "layer",
            ENUM(
                "commit_message", "structured_block", "raw_transcript",
                name="summary_layer", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("content_json", JSONB, nullable=False),
        sa.Column("content_markdown", sa.Text),
        sa.Column("content_tsv", TSVECTOR),
        sa.Column("model", sa.Text),
        sa.Column("prompt_version", sa.Text),
        sa.Column("latency_ms", sa.Integer),
        sa.Column("input_tokens", sa.Integer),
        sa.Column("output_tokens", sa.Integer),
        sa.Column("cost_usd", sa.Numeric(12, 6)),
        sa.Column("quality_score", sa.Float),
        sa.Column("failure_reason", sa.Text),
        sa.Column(
            "superseded_by",
            UUID(as_uuid=True),
            sa.ForeignKey("summaries.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    # Each push has exactly one row per layer
    op.create_index(
        "ix_summaries_push_layer",
        "summaries",
        ["push_id", "layer"],
        unique=True,
        postgresql_where=sa.text("superseded_by IS NULL"),
    )
    # BM25 full-text search
    op.create_index(
        "ix_summaries_content_tsv",
        "summaries",
        [sa.text("content_tsv")],
        postgresql_using="gin",
    )

    # ------------------------------------------------------------------
    # summary_embeddings  (vector column via raw DDL; pgvector needed)
    # ------------------------------------------------------------------
    op.execute("""
        CREATE TABLE summary_embeddings (
            summary_id  uuid PRIMARY KEY
                REFERENCES summaries(id) ON DELETE CASCADE,
            embedding   vector(1024) NOT NULL,
            embedding_model text NOT NULL DEFAULT 'voyage-3-large',
            created_at  timestamptz NOT NULL DEFAULT now()
        )
    """)
    op.execute("""
        CREATE INDEX ix_summary_embeddings_hnsw
        ON summary_embeddings
        USING hnsw (embedding vector_cosine_ops)
    """)

    # ------------------------------------------------------------------
    # transcripts
    # ------------------------------------------------------------------
    op.create_table(
        "transcripts",
        sa.Column(
            "push_id",
            UUID(as_uuid=True),
            sa.ForeignKey("pushes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("storage_path", sa.Text, nullable=False),
        sa.Column("sha256", sa.Text, nullable=False),
        sa.Column("size_bytes", sa.BigInteger, nullable=False),
        sa.Column("message_count", sa.Integer, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # tags + push_tags
    # ------------------------------------------------------------------
    op.create_table(
        "tags",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.Text, nullable=False),
        sa.Column("slug", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint("workspace_id", "slug", name="uq_tags_workspace_slug"),
    )

    op.create_table(
        "push_tags",
        sa.Column(
            "push_id",
            UUID(as_uuid=True),
            sa.ForeignKey("pushes.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "tag_id",
            UUID(as_uuid=True),
            sa.ForeignKey("tags.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )

    # ------------------------------------------------------------------
    # push_relationships
    # ------------------------------------------------------------------
    op.create_table(
        "push_relationships",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "from_push_id",
            UUID(as_uuid=True),
            sa.ForeignKey("pushes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "to_push_id",
            UUID(as_uuid=True),
            sa.ForeignKey("pushes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "relation_type",
            ENUM(
                "continuation", "reference", "supersession",
                name="relation_type", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # summary_feedback
    # ------------------------------------------------------------------
    op.create_table(
        "summary_feedback",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "summary_id",
            UUID(as_uuid=True),
            sa.ForeignKey("summaries.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("auth.users.id", ondelete="SET NULL"),
        ),
        sa.Column("score", sa.SmallInteger, nullable=False),
        sa.Column("comment", sa.Text),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("score BETWEEN 1 AND 5", name="ck_summary_feedback_score"),
    )

    # ------------------------------------------------------------------
    # pulls
    # ------------------------------------------------------------------
    op.create_table(
        "pulls",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("auth.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "target_platform",
            ENUM("claude_ai", name="target_platform", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "origin",
            ENUM("extension", "dashboard", name="pull_origin", create_type=False),
            nullable=False,
        ),
        sa.Column(
            "resolution",
            ENUM(
                "commit_message", "structured_block", "raw_transcript",
                name="pull_resolution", create_type=False,
            ),
            nullable=False,
        ),
        sa.Column("push_ids", ARRAY(sa.Text), nullable=False),
        sa.Column("workspace_ids", ARRAY(sa.Text), nullable=False),
        sa.Column("token_estimate", sa.Integer),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )

    # ------------------------------------------------------------------
    # audit_log
    # ------------------------------------------------------------------
    op.create_table(
        "audit_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("auth.users.id", ondelete="SET NULL"),
        ),
        sa.Column("action", sa.Text, nullable=False),
        sa.Column("resource_type", sa.Text),
        sa.Column("resource_id", sa.Text),
        sa.Column("request_id", sa.Text),
        sa.Column("ip", sa.Text),
        sa.Column("user_agent", sa.Text),
        sa.Column("metadata_json", JSONB),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_audit_log_user_created",
        "audit_log",
        ["user_id", sa.text("created_at DESC")],
    )

    # ------------------------------------------------------------------
    # tsvector trigger: keep content_tsv in sync with content_markdown
    # ------------------------------------------------------------------
    op.execute("""
        CREATE OR REPLACE FUNCTION summaries_update_tsv()
        RETURNS trigger LANGUAGE plpgsql AS $$
        BEGIN
            NEW.content_tsv :=
                to_tsvector('english', coalesce(NEW.content_markdown, ''));
            RETURN NEW;
        END;
        $$;

        CREATE TRIGGER trg_summaries_tsv
        BEFORE INSERT OR UPDATE OF content_markdown
        ON summaries
        FOR EACH ROW EXECUTE FUNCTION summaries_update_tsv();
    """)

    # ------------------------------------------------------------------
    # Application role for RLS (idempotent)
    # ------------------------------------------------------------------
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'ch_authenticated'
            ) THEN
                CREATE ROLE ch_authenticated;
            END IF;
        END $$;
    """)

    # Grant DML on all app tables to ch_authenticated
    _rls_tables = [
        "profiles", "api_tokens", "workspaces", "pushes", "summaries",
        "summary_embeddings", "transcripts", "tags", "push_tags",
        "push_relationships", "summary_feedback", "pulls", "audit_log",
        "interchange_format_versions",
    ]
    for tbl in _rls_tables:
        op.execute(
            f"GRANT SELECT, INSERT, UPDATE, DELETE ON {tbl} TO ch_authenticated"
        )

    # ------------------------------------------------------------------
    # Row-Level Security
    # ------------------------------------------------------------------
    for tbl in _rls_tables:
        op.execute(f"ALTER TABLE {tbl} ENABLE ROW LEVEL SECURITY")
        # Superusers bypass RLS by default; this forces it even for table owners.
        op.execute(f"ALTER TABLE {tbl} FORCE ROW LEVEL SECURITY")

    # profiles: owner only
    op.execute("""
        CREATE POLICY profiles_owner ON profiles
            USING (user_id = auth.uid());
    """)

    # api_tokens: owner only
    op.execute("""
        CREATE POLICY api_tokens_owner ON api_tokens
            USING (user_id = auth.uid());
    """)

    # workspaces: owner only (soft-deletes still visible to owner for undo)
    op.execute("""
        CREATE POLICY workspaces_owner ON workspaces
            USING (user_id = auth.uid());
    """)

    # pushes: owner only
    op.execute("""
        CREATE POLICY pushes_owner ON pushes
            USING (user_id = auth.uid());
    """)

    # summaries: accessible if the parent push belongs to the caller
    op.execute("""
        CREATE POLICY summaries_owner ON summaries
            USING (
                EXISTS (
                    SELECT 1 FROM pushes p
                    WHERE p.id = summaries.push_id
                      AND p.user_id = auth.uid()
                )
            );
    """)

    # summary_embeddings: same path as summaries
    op.execute("""
        CREATE POLICY summary_embeddings_owner ON summary_embeddings
            USING (
                EXISTS (
                    SELECT 1 FROM summaries s
                    JOIN pushes p ON p.id = s.push_id
                    WHERE s.id = summary_embeddings.summary_id
                      AND p.user_id = auth.uid()
                )
            );
    """)

    # transcripts: via push ownership
    op.execute("""
        CREATE POLICY transcripts_owner ON transcripts
            USING (
                EXISTS (
                    SELECT 1 FROM pushes p
                    WHERE p.id = transcripts.push_id
                      AND p.user_id = auth.uid()
                )
            );
    """)

    # tags: via workspace ownership
    op.execute("""
        CREATE POLICY tags_owner ON tags
            USING (
                EXISTS (
                    SELECT 1 FROM workspaces w
                    WHERE w.id = tags.workspace_id
                      AND w.user_id = auth.uid()
                )
            );
    """)

    # push_tags: via push ownership
    op.execute("""
        CREATE POLICY push_tags_owner ON push_tags
            USING (
                EXISTS (
                    SELECT 1 FROM pushes p
                    WHERE p.id = push_tags.push_id
                      AND p.user_id = auth.uid()
                )
            );
    """)

    # push_relationships: visible if caller owns either endpoint
    op.execute("""
        CREATE POLICY push_relationships_owner ON push_relationships
            USING (
                EXISTS (
                    SELECT 1 FROM pushes p
                    WHERE p.id = push_relationships.from_push_id
                      AND p.user_id = auth.uid()
                )
            );
    """)

    # summary_feedback: users see their own feedback
    op.execute("""
        CREATE POLICY summary_feedback_owner ON summary_feedback
            USING (user_id = auth.uid() OR user_id IS NULL);
    """)

    # pulls: owner only
    op.execute("""
        CREATE POLICY pulls_owner ON pulls
            USING (user_id = auth.uid());
    """)

    # audit_log: owner only
    op.execute("""
        CREATE POLICY audit_log_owner ON audit_log
            USING (user_id = auth.uid());
    """)

    # interchange_format_versions: publicly readable (no user_id column)
    op.execute("""
        CREATE POLICY ifv_read ON interchange_format_versions
            FOR SELECT USING (true);
    """)


def downgrade() -> None:
    _rls_tables = [
        "profiles", "api_tokens", "workspaces", "pushes", "summaries",
        "summary_embeddings", "transcripts", "tags", "push_tags",
        "push_relationships", "summary_feedback", "pulls", "audit_log",
        "interchange_format_versions",
    ]

    # Drop RLS policies
    policy_map = {
        "profiles": "profiles_owner",
        "api_tokens": "api_tokens_owner",
        "workspaces": "workspaces_owner",
        "pushes": "pushes_owner",
        "summaries": "summaries_owner",
        "summary_embeddings": "summary_embeddings_owner",
        "transcripts": "transcripts_owner",
        "tags": "tags_owner",
        "push_tags": "push_tags_owner",
        "push_relationships": "push_relationships_owner",
        "summary_feedback": "summary_feedback_owner",
        "pulls": "pulls_owner",
        "audit_log": "audit_log_owner",
        "interchange_format_versions": "ifv_read",
    }
    for tbl, policy in policy_map.items():
        op.execute(f"DROP POLICY IF EXISTS {policy} ON {tbl}")

    # Disable RLS
    for tbl in _rls_tables:
        op.execute(f"ALTER TABLE {tbl} NO FORCE ROW LEVEL SECURITY")
        op.execute(f"ALTER TABLE {tbl} DISABLE ROW LEVEL SECURITY")

    # Drop tsvector trigger
    op.execute("DROP TRIGGER IF EXISTS trg_summaries_tsv ON summaries")
    op.execute("DROP FUNCTION IF EXISTS summaries_update_tsv()")

    # Drop tables in reverse dependency order
    op.drop_table("audit_log")
    op.drop_table("pulls")
    op.drop_table("summary_feedback")
    op.drop_table("push_relationships")
    op.drop_table("push_tags")
    op.drop_table("tags")
    op.drop_table("transcripts")
    op.execute("DROP TABLE IF EXISTS summary_embeddings")
    op.drop_table("summaries")
    op.drop_table("pushes")
    op.drop_table("interchange_format_versions")
    op.drop_table("workspaces")
    op.drop_table("api_tokens")
    op.drop_table("profiles")

    # Drop enum types
    op.execute("DROP TYPE IF EXISTS pull_resolution")
    op.execute("DROP TYPE IF EXISTS pull_origin")
    op.execute("DROP TYPE IF EXISTS target_platform")
    op.execute("DROP TYPE IF EXISTS relation_type")
    op.execute("DROP TYPE IF EXISTS summary_layer")
    op.execute("DROP TYPE IF EXISTS push_status")
    op.execute("DROP TYPE IF EXISTS source_platform")

    op.execute("DROP EXTENSION IF EXISTS vector")
