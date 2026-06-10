"""Push shares: share a push's summary with another user.

Revision ID: 006_push_shares
Revises: 005
Create Date: 2026-06-10

Adds the push_shares table plus the RLS surface that makes sharing work:

  - push_shares rows are managed by the owner (full DML) and visible to the
    recipient (SELECT, plus DELETE so a recipient can remove a share from
    their own dashboard).
  - pushes/summaries gain additional FOR SELECT policies so a recipient can
    read a shared push and its summary layers. The raw_transcript layer is
    explicitly excluded — sharing grants access to the summary, never the
    transcript (transcripts keep their owner-only policy untouched).
  - Two SECURITY DEFINER helpers expose the minimal auth.users lookups the
    share endpoints need (email -> id at share time, id -> email for display)
    without granting any role direct access to auth.users.

Policy references must be acyclic at the relation level: pushes' shared-read
policy queries push_shares, so push_shares' own policies must not query
pushes directly (Postgres raises "infinite recursion detected in policy"
otherwise). The ownership check in push_shares' WITH CHECK therefore goes
through ch_push_owned_by(), a SECURITY DEFINER plpgsql function (plpgsql so
it can never be inlined back into the policy expression; its owner bypasses
RLS, which both breaks the cycle and gives the correct answer). The check
itself guards against direct PostgREST inserts on Supabase — a user must own
a push to share it, and RLS, not just the API layer, must enforce that.

Also creates the `authenticated` role when missing: Supabase provides it
natively (with default-privilege grants), but local/CI Postgres only has
ch_authenticated, while the API's get_rls_session does SET LOCAL ROLE
authenticated. Granting ch_authenticated membership gives it the same table
privileges via inheritance.
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

# revision identifiers, used by Alembic.
revision = "006_push_shares"
down_revision = "005"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""
        DO $$
        BEGIN
            IF NOT EXISTS (
                SELECT 1 FROM pg_roles WHERE rolname = 'authenticated'
            ) THEN
                CREATE ROLE authenticated NOLOGIN;
                GRANT ch_authenticated TO authenticated;
            END IF;
        END $$;
    """)

    op.create_table(
        "push_shares",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "push_id",
            UUID(as_uuid=True),
            sa.ForeignKey("pushes.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "owner_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("auth.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "recipient_user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("auth.users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("owner_email", sa.Text, nullable=False),
        sa.Column("recipient_email", sa.Text, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.UniqueConstraint(
            "push_id", "recipient_user_id", name="uq_push_shares_push_recipient"
        ),
    )
    op.create_index("ix_push_shares_push_id", "push_shares", ["push_id"])
    op.create_index("ix_push_shares_recipient_user_id", "push_shares", ["recipient_user_id"])

    op.execute("GRANT SELECT, INSERT, UPDATE, DELETE ON push_shares TO ch_authenticated")
    op.execute("ALTER TABLE push_shares ENABLE ROW LEVEL SECURITY")
    op.execute("ALTER TABLE push_shares FORCE ROW LEVEL SECURITY")

    op.execute("""
        CREATE OR REPLACE FUNCTION public.ch_push_owned_by(p_push_id uuid, p_user_id uuid)
            RETURNS boolean
            LANGUAGE plpgsql STABLE SECURITY DEFINER
            SET search_path = ''
        AS $$
        BEGIN
            RETURN EXISTS (
                SELECT 1 FROM public.pushes p
                WHERE p.id = p_push_id
                  AND p.user_id = p_user_id
                  AND p.deleted_at IS NULL
            );
        END
        $$;
    """)

    op.execute("""
        CREATE POLICY push_shares_owner ON push_shares
            USING (owner_user_id = auth.uid())
            WITH CHECK (
                owner_user_id = auth.uid()
                AND public.ch_push_owned_by(push_id, auth.uid())
            );
    """)
    op.execute("""
        CREATE POLICY push_shares_recipient_read ON push_shares
            FOR SELECT USING (recipient_user_id = auth.uid());
    """)
    op.execute("""
        CREATE POLICY push_shares_recipient_delete ON push_shares
            FOR DELETE USING (recipient_user_id = auth.uid());
    """)

    # Recipients can read shared pushes and their summary layers (transcript
    # excluded). These are additive FOR SELECT policies; the existing owner
    # policies keep governing writes.
    op.execute("""
        CREATE POLICY pushes_shared_read ON pushes
            FOR SELECT USING (
                EXISTS (
                    SELECT 1 FROM push_shares ps
                    WHERE ps.push_id = pushes.id
                      AND ps.recipient_user_id = auth.uid()
                )
            );
    """)
    op.execute("""
        CREATE POLICY summaries_shared_read ON summaries
            FOR SELECT USING (
                layer <> 'raw_transcript'
                AND EXISTS (
                    SELECT 1 FROM push_shares ps
                    WHERE ps.push_id = summaries.push_id
                      AND ps.recipient_user_id = auth.uid()
                )
            );
    """)

    op.execute("""
        CREATE OR REPLACE FUNCTION public.ch_user_id_by_email(p_email text)
            RETURNS uuid
            LANGUAGE sql STABLE SECURITY DEFINER
            SET search_path = ''
        AS $$
            SELECT id FROM auth.users WHERE lower(email) = lower(p_email) LIMIT 1
        $$;
    """)
    op.execute("""
        CREATE OR REPLACE FUNCTION public.ch_user_email_by_id(p_user_id uuid)
            RETURNS text
            LANGUAGE sql STABLE SECURITY DEFINER
            SET search_path = ''
        AS $$
            SELECT email FROM auth.users WHERE id = p_user_id
        $$;
    """)
    for fn in (
        "ch_user_id_by_email(text)",
        "ch_user_email_by_id(uuid)",
        "ch_push_owned_by(uuid, uuid)",
    ):
        op.execute(f"REVOKE ALL ON FUNCTION public.{fn} FROM PUBLIC")
        op.execute(f"GRANT EXECUTE ON FUNCTION public.{fn} TO ch_authenticated, authenticated")


def downgrade() -> None:
    op.execute("DROP FUNCTION IF EXISTS public.ch_user_id_by_email(text)")
    op.execute("DROP FUNCTION IF EXISTS public.ch_user_email_by_id(uuid)")
    op.execute("DROP POLICY IF EXISTS push_shares_owner ON push_shares")
    op.execute("DROP FUNCTION IF EXISTS public.ch_push_owned_by(uuid, uuid)")
    op.execute("DROP POLICY IF EXISTS summaries_shared_read ON summaries")
    op.execute("DROP POLICY IF EXISTS pushes_shared_read ON pushes")
    op.execute("DROP POLICY IF EXISTS push_shares_recipient_delete ON push_shares")
    op.execute("DROP POLICY IF EXISTS push_shares_recipient_read ON push_shares")
    op.execute("ALTER TABLE push_shares DISABLE ROW LEVEL SECURITY")
    op.drop_index("ix_push_shares_recipient_user_id", table_name="push_shares")
    op.drop_index("ix_push_shares_push_id", table_name="push_shares")
    op.drop_table("push_shares")
    # The `authenticated` role is left in place: cluster-wide, idempotent to
    # recreate, and other sessions may reference it.
