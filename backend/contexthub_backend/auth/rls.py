"""RLS helpers for non-FastAPI contexts (ARQ workers, scripts)."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def apply_rls_context(session: AsyncSession, *, user_id: uuid.UUID) -> None:
    """Set the per-transaction RLS context for `user_id`.

    Single source of truth shared by the API request path (`get_rls_session` in
    `auth.dependencies`) and worker jobs, so the two can never drift again.

    Switch to Supabase's built-in `authenticated` role and set
    `request.jwt.claim.sub` so the RLS policies' `auth.uid()` resolves to our
    user; also set `app.current_user_id` for any policies/triggers that read it
    directly. Must run inside an open transaction (SET LOCAL is txn-scoped).
    """
    await session.execute(text("SET LOCAL ROLE authenticated"))
    await session.execute(
        text("SELECT set_config('request.jwt.claim.sub', :uid, true)"),
        {"uid": str(user_id)},
    )
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": str(user_id)},
    )
