"""add new summary and pull enum layers

Revision ID: 002_add_new_summary_layers
Revises: 001_initial_schema
Create Date: 2026-04-28 18:47:00.000000
"""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "002_add_new_summary_layers"
down_revision = "001"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE summary_layer ADD VALUE IF NOT EXISTS 'title'")
    op.execute("ALTER TYPE summary_layer ADD VALUE IF NOT EXISTS 'summary'")
    op.execute("ALTER TYPE summary_layer ADD VALUE IF NOT EXISTS 'details'")
    op.execute("ALTER TYPE pull_resolution ADD VALUE IF NOT EXISTS 'title'")
    op.execute("ALTER TYPE pull_resolution ADD VALUE IF NOT EXISTS 'summary'")
    op.execute("ALTER TYPE pull_resolution ADD VALUE IF NOT EXISTS 'details'")


def downgrade() -> None:
    # PostgreSQL enum values cannot be removed safely in-place.
    pass

