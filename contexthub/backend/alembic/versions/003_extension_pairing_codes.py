"""add extension pairing codes table

Revision ID: 003_extension_pairing_codes
Revises: 002_add_new_summary_layers
Create Date: 2026-04-29 15:15:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import ARRAY, UUID

# revision identifiers, used by Alembic.
revision = "003_extension_pairing_codes"
down_revision = "002_add_new_summary_layers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "extension_pairing_codes",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("auth.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "workspace_id",
            UUID(as_uuid=True),
            sa.ForeignKey("workspaces.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("token_name", sa.Text, nullable=False),
        sa.Column("code_hash", sa.Text, nullable=False),
        sa.Column("scopes", ARRAY(sa.Text), nullable=False),
        sa.Column("api_base_url", sa.Text),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("consumed_at", sa.DateTime(timezone=True)),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_index(
        "ix_extension_pairing_codes_code_hash",
        "extension_pairing_codes",
        ["code_hash"],
        unique=True,
    )
    op.create_index(
        "ix_extension_pairing_codes_expires_at",
        "extension_pairing_codes",
        ["expires_at"],
        unique=False,
    )

    op.execute(
        "GRANT SELECT, INSERT, UPDATE, DELETE ON extension_pairing_codes TO ch_authenticated"
    )
    op.execute("ALTER TABLE extension_pairing_codes ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE extension_pairing_codes FORCE ROW LEVEL SECURITY")
    op.execute("""
        CREATE POLICY extension_pairing_codes_owner ON extension_pairing_codes
            USING (user_id = auth.uid());
    """)


def downgrade() -> None:
    op.execute(
        "DROP POLICY IF EXISTS extension_pairing_codes_owner ON extension_pairing_codes"
    )
    op.execute("ALTER TABLE extension_pairing_codes DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_extension_pairing_codes_expires_at", table_name="extension_pairing_codes")
    op.drop_index("ix_extension_pairing_codes_code_hash", table_name="extension_pairing_codes")
    op.drop_table("extension_pairing_codes")
