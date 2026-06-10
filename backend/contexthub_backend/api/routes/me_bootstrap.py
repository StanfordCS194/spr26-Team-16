"""POST /v1/me/bootstrap — idempotent first-call setup for an authenticated user.

When the extension or dashboard signs the user in via Supabase OAuth, Supabase
creates the auth.users row and issues a JWT — but our app-level rows (profile,
default workspace) don't exist yet. This endpoint creates them on first call
and is a no-op on subsequent calls.

Returns the workspace_id the client needs for push/pull/search calls, plus
the user's display info (mirrored from Google via Supabase user metadata, if
present, else derived from email).

Auth: Supabase JWT only (require_jwt). API tokens cannot bootstrap.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.auth.dependencies import (
    AuthUser,
    get_current_user,
    get_rls_session,
    require_jwt,
)
from contexthub_backend.db.models import Profile, Workspace
from contexthub_backend.schemas.me_bootstrap import (
    MeBootstrapRequest,
    MeBootstrapResponse,
    MeBootstrapUser,
)

router = APIRouter(tags=["auth"])


def _slugify_email(email: str) -> str:
    local = email.split("@", 1)[0].lower()
    safe = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in local)
    return safe.strip("-") or "default"


@router.post("/me/bootstrap", response_model=MeBootstrapResponse)
async def me_bootstrap(
    body: MeBootstrapRequest,
    user: Annotated[AuthUser, Depends(require_jwt)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    _identity: Annotated[AuthUser, Depends(get_current_user)],
) -> MeBootstrapResponse:
    # Profile (idempotent).
    profile_row = (
        await session.execute(select(Profile).where(Profile.user_id == user.user_id))
    ).scalar_one_or_none()
    if profile_row is None:
        profile_row = Profile(
            user_id=user.user_id,
            display_name=body.display_name or (body.email.split("@", 1)[0] if body.email else None),
            avatar_url=body.avatar_url,
        )
        session.add(profile_row)
        await session.flush()
    else:
        if body.display_name and profile_row.display_name != body.display_name:
            profile_row.display_name = body.display_name
        if body.avatar_url and profile_row.avatar_url != body.avatar_url:
            profile_row.avatar_url = body.avatar_url

    # Default workspace (idempotent).
    workspace_row = (
        await session.execute(
            select(Workspace).where(Workspace.user_id == user.user_id).limit(1)
        )
    ).scalar_one_or_none()
    if workspace_row is None:
        slug = _slugify_email(body.email or "personal")
        workspace_row = Workspace(
            user_id=user.user_id,
            name="Personal",
            slug=slug,
        )
        session.add(workspace_row)
        await session.flush()

    return MeBootstrapResponse(
        user=MeBootstrapUser(
            user_id=str(user.user_id),
            email=body.email,
            display_name=profile_row.display_name,
            avatar_url=profile_row.avatar_url,
        ),
        workspace_id=str(workspace_row.id),
    )
