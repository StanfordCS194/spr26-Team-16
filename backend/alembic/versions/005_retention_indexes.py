"""Indexes supporting retention purge queries (ARCHITECTURE.md §13).

Each purge job filters on a column that wasn't indexed in the initial schema
because the row counts were small. As the tables grow these become required:

- pushes(deleted_at) — `purge_soft_deleted_pushes` cutoff scan
- pushes(status, created_at) — `purge_failed_pushes` partial-index target
- pushes(status, updated_at) — stuck-push detection
- audit_log(created_at) — `purge_audit_log` cutoff scan
- api_tokens(revoked_at) — `purge_revoked_tokens` cutoff scan

The pushes(status, created_at) index is partial on status='failed' to keep it
small (failed pushes are a tiny minority of the table).

Revision ID: 005
Revises: 004
Create Date: 2026-05-05
"""

from alembic import op


revision = "005"
down_revision = "004"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pushes_deleted_at "
        "ON pushes (deleted_at) WHERE deleted_at IS NOT NULL"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pushes_failed_created_at "
        "ON pushes (created_at) WHERE status = 'failed'"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_pushes_pending_updated_at "
        "ON pushes (updated_at) WHERE status IN ('pending', 'processing')"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_audit_log_created_at "
        "ON audit_log (created_at)"
    )
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_api_tokens_revoked_at "
        "ON api_tokens (revoked_at) WHERE revoked_at IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_api_tokens_revoked_at")
    op.execute("DROP INDEX IF EXISTS idx_audit_log_created_at")
    op.execute("DROP INDEX IF EXISTS idx_pushes_pending_updated_at")
    op.execute("DROP INDEX IF EXISTS idx_pushes_failed_created_at")
    op.execute("DROP INDEX IF EXISTS idx_pushes_deleted_at")
