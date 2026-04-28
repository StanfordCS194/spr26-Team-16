"""RLS helpers for non-FastAPI contexts (ARQ workers, scripts)."""

from __future__ import annotations

import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def apply_rls_context(session: AsyncSession, *, user_id: uuid.UUID) -> None:
    """Match `get_rls_session` in `auth.dependencies` for worker jobs."""
    await session.execute(text("SET LOCAL ROLE ch_authenticated"))
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": str(user_id)},
    )
