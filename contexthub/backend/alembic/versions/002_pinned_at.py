"""Add pushes.pinned_at + partial index for pinned-first listing.

Revision ID: 002
Revises: 001
Create Date: 2026-05-23
"""

from alembic import op
import sqlalchemy as sa

revision = "002"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "pushes",
        sa.Column("pinned_at", sa.DateTime(timezone=True), nullable=True),
    )
    # Pinned-first listing within a workspace; partial keeps the index small.
    op.create_index(
        "ix_pushes_pinned",
        "pushes",
        ["workspace_id", sa.text("pinned_at DESC")],
        postgresql_where=sa.text("pinned_at IS NOT NULL AND deleted_at IS NULL"),
    )


def downgrade() -> None:
    op.drop_index("ix_pushes_pinned", table_name="pushes")
    op.drop_column("pushes", "pinned_at")
