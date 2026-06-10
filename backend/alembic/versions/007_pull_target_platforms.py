"""Add 'chatgpt' and 'gemini' to the target_platform enum.

The initial schema (001) created `target_platform AS ENUM ('claude_ai')` while
`source_platform` already had all three platforms. The pull API and context
builder were later extended to accept 'chatgpt' and 'gemini' as targets
(schemas/pulls.py validates `^(claude_ai|chatgpt|gemini)$`), but the enum was
never backfilled — so `POST /v1/pulls` with target_platform='chatgpt' raised
`invalid input value for enum target_platform` and returned HTTP 500.

ADD VALUE IF NOT EXISTS is idempotent and additive (existing rows/readers are
unaffected). Postgres cannot drop enum values, so downgrade is a no-op.

Revision ID: 007_pull_target_platforms
Revises: 006_push_shares
Create Date: 2026-06-10
"""

from alembic import op


revision = "007_pull_target_platforms"
down_revision = "006_push_shares"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("ALTER TYPE target_platform ADD VALUE IF NOT EXISTS 'chatgpt'")
    op.execute("ALTER TYPE target_platform ADD VALUE IF NOT EXISTS 'gemini'")


def downgrade() -> None:
    # Postgres has no DROP VALUE; removing an enum member requires recreating the
    # type and rewriting every dependent column. This addition is safe to leave.
    pass
