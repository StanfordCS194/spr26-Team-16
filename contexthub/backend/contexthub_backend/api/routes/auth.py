"""Auth & identity endpoints — §7 Auth & identity (ARCHITECTURE.md).

GET  /v1/me            — current user profile
POST /v1/tokens        — mint API token (JWT auth required)
GET  /v1/tokens        — list caller's non-revoked tokens
DELETE /v1/tokens/{id} — revoke a token
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.api.errors import NotFoundError
from contexthub_backend.auth.dependencies import (
    AuthUser,
    get_current_user,
    get_rls_session,
    require_jwt,
)
from contexthub_backend.auth.tokens import mint_token, revoke_token
from contexthub_backend.db.models import ApiToken, Profile
from contexthub_backend.schemas.auth import (
    MeResponse,
    TokenCreateRequest,
    TokenMintResponse,
    TokenRow,
)

router = APIRouter(tags=["auth"])


@router.get("/me", response_model=MeResponse)
async def get_me(
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> MeResponse:
    result = await session.execute(
        select(Profile).where(Profile.user_id == user.user_id)
    )
    profile = result.scalar_one_or_none()
    return MeResponse(
        user_id=str(user.user_id),
        display_name=profile.display_name if profile else None,
        avatar_url=profile.avatar_url if profile else None,
    )


@router.post("/tokens", response_model=TokenMintResponse, status_code=201)
async def create_token(
    body: TokenCreateRequest,
    user: Annotated[AuthUser, Depends(require_jwt)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> TokenMintResponse:
    """Mint a new API token. Raw token is returned once and never stored."""
    row, raw = await mint_token(
        user_id=user.user_id,
        name=body.name,
        scopes=body.scopes,
        session=session,
    )
    return TokenMintResponse(
        id=str(row.id),
        name=row.name,
        scopes=row.scopes,
        created_at=row.created_at,
        last_used_at=row.last_used_at,
        revoked_at=row.revoked_at,
        token=raw,
    )


@router.get("/tokens", response_model=list[TokenRow])
async def list_tokens(
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> list[TokenRow]:
    result = await session.execute(
        select(ApiToken)
        .where(
            ApiToken.user_id == user.user_id,
            ApiToken.revoked_at.is_(None),
        )
        .order_by(ApiToken.created_at.desc())
    )
    rows = result.scalars().all()
    return [
        TokenRow(
            id=str(r.id),
            name=r.name,
            scopes=r.scopes,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
            revoked_at=r.revoked_at,
        )
        for r in rows
    ]


@router.delete("/tokens/{token_id}", status_code=204)
async def delete_token(
    token_id: uuid.UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> None:
    await revoke_token(
        token_id=token_id,
        requesting_user_id=user.user_id,
        session=session,
    )
