"""Add WITH CHECK clauses to RLS policies so INSERTs work.

Revision ID: 003_fix_rls_with_check
Revises: 002_add_new_summary_layers
Create Date: 2026-05-04

The original 001_initial_schema.py created policies with USING only — that's
sufficient for SELECT/UPDATE/DELETE but Postgres requires WITH CHECK for
INSERTs to be allowed. Add WITH CHECK to all owner policies so the bootstrap
endpoint (and any future INSERT) can succeed under RLS.
"""

from __future__ import annotations

from alembic import op

revision = "003_fix_rls_with_check"
down_revision = "002_add_new_summary_layers"
branch_labels = None
depends_on = None


# (table, policy_name, using_expr, with_check_expr)
_OWNER_POLICIES = [
    ("profiles", "profiles_owner", "user_id = auth.uid()", "user_id = auth.uid()"),
    ("api_tokens", "api_tokens_owner", "user_id = auth.uid()", "user_id = auth.uid()"),
    ("workspaces", "workspaces_owner", "user_id = auth.uid()", "user_id = auth.uid()"),
    ("pushes", "pushes_owner", "user_id = auth.uid()", "user_id = auth.uid()"),
    (
        "summaries",
        "summaries_owner",
        "EXISTS (SELECT 1 FROM pushes p WHERE p.id = summaries.push_id AND p.user_id = auth.uid())",
        "EXISTS (SELECT 1 FROM pushes p WHERE p.id = summaries.push_id AND p.user_id = auth.uid())",
    ),
    (
        "summary_embeddings",
        "summary_embeddings_owner",
        "EXISTS (SELECT 1 FROM summaries s JOIN pushes p ON p.id = s.push_id WHERE s.id = summary_embeddings.summary_id AND p.user_id = auth.uid())",
        "EXISTS (SELECT 1 FROM summaries s JOIN pushes p ON p.id = s.push_id WHERE s.id = summary_embeddings.summary_id AND p.user_id = auth.uid())",
    ),
    (
        "transcripts",
        "transcripts_owner",
        "EXISTS (SELECT 1 FROM pushes p WHERE p.id = transcripts.push_id AND p.user_id = auth.uid())",
        "EXISTS (SELECT 1 FROM pushes p WHERE p.id = transcripts.push_id AND p.user_id = auth.uid())",
    ),
    (
        "tags",
        "tags_owner",
        "EXISTS (SELECT 1 FROM workspaces w WHERE w.id = tags.workspace_id AND w.user_id = auth.uid())",
        "EXISTS (SELECT 1 FROM workspaces w WHERE w.id = tags.workspace_id AND w.user_id = auth.uid())",
    ),
    (
        "push_tags",
        "push_tags_owner",
        "EXISTS (SELECT 1 FROM pushes p WHERE p.id = push_tags.push_id AND p.user_id = auth.uid())",
        "EXISTS (SELECT 1 FROM pushes p WHERE p.id = push_tags.push_id AND p.user_id = auth.uid())",
    ),
    (
        "push_relationships",
        "push_relationships_owner",
        "EXISTS (SELECT 1 FROM pushes p WHERE p.id = push_relationships.from_push_id AND p.user_id = auth.uid())",
        "EXISTS (SELECT 1 FROM pushes p WHERE p.id = push_relationships.from_push_id AND p.user_id = auth.uid())",
    ),
    (
        "summary_feedback",
        "summary_feedback_owner",
        "user_id = auth.uid() OR user_id IS NULL",
        "user_id = auth.uid() OR user_id IS NULL",
    ),
    ("pulls", "pulls_owner", "user_id = auth.uid()", "user_id = auth.uid()"),
    ("audit_log", "audit_log_owner", "user_id = auth.uid()", "user_id = auth.uid()"),
]


def upgrade() -> None:
    for table, name, using, with_check in _OWNER_POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
        op.execute(
            f"CREATE POLICY {name} ON {table} "
            f"USING ({using}) WITH CHECK ({with_check})"
        )


def downgrade() -> None:
    for table, name, using, _with_check in _OWNER_POLICIES:
        op.execute(f"DROP POLICY IF EXISTS {name} ON {table}")
        op.execute(f"CREATE POLICY {name} ON {table} USING ({using})")
