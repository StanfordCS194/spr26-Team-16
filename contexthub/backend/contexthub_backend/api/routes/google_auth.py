"""Google sign-in: exchange a Google ID token for a ch_ API token.

Endpoint: POST /v1/auth/google
Body:     { "id_token": "<google-id-token>" }
Returns:  { "token": "ch_...", "scopes": [...], "workspace_id": "...", "user": {...} }

This replaces the dashboard pairing-code dance for the extension. The extension
calls chrome.identity.getAuthToken to obtain a Google ID token, then POSTs it
here. Same Google account always resolves to the same internal user_id, so the
user sees their full history on any device after a single sign-in.

Implementation notes:
  - User identity: user_id = uuid5(NAMESPACE, google_sub) — deterministic.
  - In dev, auth.users is a stub table; we upsert directly so FK constraints
    succeed. In production Supabase, auth.users is owned by the platform —
    this endpoint should be paired with a Supabase Admin API call to create
    the user there. v0 keeps it simple and matches dev behavior.
  - Workspace bootstrap: a default workspace is created on first sign-in so
    the user can immediately push/pull.
  - Token scopes: the full set (push, pull, search, read).
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.auth.dependencies import get_db_session
from contexthub_backend.auth.google import (
    GoogleIdentity,
    configured_client_ids,
    verify_google_id_token,
)
from contexthub_backend.auth.tokens import ALL_SCOPES, mint_token
from contexthub_backend.config import settings
from contexthub_backend.db.models import Profile, Workspace
from contexthub_backend.schemas.google_auth import (
    GoogleAuthRequest,
    GoogleAuthResponse,
    GoogleAuthUser,
)

router = APIRouter(tags=["auth"])


def _slugify_email(email: str) -> str:
    local = email.split("@", 1)[0].lower()
    safe = "".join(ch if ch.isalnum() or ch == "-" else "-" for ch in local)
    return safe.strip("-") or "default"


async def _ensure_auth_user(session: AsyncSession, identity: GoogleIdentity) -> None:
    """Ensure a row exists in auth.users for this user_id.

    In production Supabase, this is a no-op (the row is created by the platform
    via Supabase Admin API in a separate path). In dev/test the auth.users
    stub is writable and we upsert here so FK constraints (api_tokens, profiles,
    workspaces) succeed on first sign-in.
    """
    await session.execute(
        text(
            "INSERT INTO auth.users (id, email) VALUES (:uid, :email) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"uid": str(identity.user_id), "email": identity.email},
    )


async def _ensure_profile(session: AsyncSession, identity: GoogleIdentity) -> Profile:
    result = await session.execute(
        select(Profile).where(Profile.user_id == identity.user_id)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        # Refresh display_name / avatar from latest Google claims.
        if identity.name and existing.display_name != identity.name:
            existing.display_name = identity.name
        if identity.picture and existing.avatar_url != identity.picture:
            existing.avatar_url = identity.picture
        return existing

    profile = Profile(
        user_id=identity.user_id,
        display_name=identity.name or identity.email,
        avatar_url=identity.picture,
    )
    session.add(profile)
    await session.flush()
    return profile


async def _ensure_default_workspace(session: AsyncSession, identity: GoogleIdentity) -> Workspace:
    result = await session.execute(
        select(Workspace).where(Workspace.user_id == identity.user_id).limit(1)
    )
    existing = result.scalar_one_or_none()
    if existing is not None:
        return existing

    slug = _slugify_email(identity.email)
    workspace = Workspace(
        user_id=identity.user_id,
        name="Personal",
        slug=slug,
    )
    session.add(workspace)
    await session.flush()
    return workspace


@router.post("/auth/google", response_model=GoogleAuthResponse)
async def auth_google(
    body: GoogleAuthRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> GoogleAuthResponse:
    audiences = configured_client_ids(settings.google_oauth_client_ids)
    identity = verify_google_id_token(body.id_token, audiences)

    # Order matters: auth.users → profile → workspace → api_token (FK chain).
    await _ensure_auth_user(session, identity)
    await _ensure_profile(session, identity)
    workspace = await _ensure_default_workspace(session, identity)

    _, raw_token = await mint_token(
        user_id=identity.user_id,
        name=body.token_name or "google-signin",
        scopes=list(ALL_SCOPES),
        session=session,
    )

    return GoogleAuthResponse(
        token=raw_token,
        scopes=list(ALL_SCOPES),
        workspace_id=str(workspace.id),
        user=GoogleAuthUser(
            user_id=str(identity.user_id),
            email=identity.email,
            display_name=identity.name,
            avatar_url=identity.picture,
        ),
    )
