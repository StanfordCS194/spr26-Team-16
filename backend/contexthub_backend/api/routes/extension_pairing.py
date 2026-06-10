"""Extension pairing flow for dashboard-to-extension token handoff."""

from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.api.errors import AuthError
from contexthub_backend.auth.dependencies import AuthUser, get_db_session, get_rls_session, require_jwt
from contexthub_backend.auth.tokens import mint_token
from contexthub_backend.config import settings
from contexthub_backend.db.models import ExtensionPairingCode, Workspace
from contexthub_backend.schemas.auth import (
    ExtensionPairingCreateRequest,
    ExtensionPairingCreateResponse,
    ExtensionPairingExchangeRequest,
    ExtensionPairingExchangeResponse,
)

_PAIRING_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
_PAIRING_CODE_LENGTH = 8

router = APIRouter(tags=["auth"])


def _hash_pairing_code(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def _generate_pairing_code() -> str:
    return "".join(secrets.choice(_PAIRING_ALPHABET) for _ in range(_PAIRING_CODE_LENGTH))


@router.post("/extension-pairing-codes", response_model=ExtensionPairingCreateResponse, status_code=201)
async def create_extension_pairing_code(
    body: ExtensionPairingCreateRequest,
    user: Annotated[AuthUser, Depends(require_jwt)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> ExtensionPairingCreateResponse:
    ttl_seconds = body.ttl_seconds or settings.pairing_code_ttl_seconds
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=ttl_seconds)

    if body.workspace_id is not None:
        workspace_result = await session.execute(
            select(Workspace).where(Workspace.id == body.workspace_id)
        )
        if workspace_result.scalar_one_or_none() is None:
            raise AuthError("workspace not found for current user")

    raw_code = _generate_pairing_code()
    row = ExtensionPairingCode(
        user_id=user.user_id,
        workspace_id=body.workspace_id,
        token_name=body.token_name,
        code_hash=_hash_pairing_code(raw_code),
        scopes=body.scopes,
        api_base_url=body.api_base_url,
        expires_at=expires_at,
    )
    session.add(row)
    await session.flush()
    return ExtensionPairingCreateResponse(code=raw_code, expires_at=expires_at)


@router.post("/extension-pairing-codes/exchange", response_model=ExtensionPairingExchangeResponse)
async def exchange_extension_pairing_code(
    body: ExtensionPairingExchangeRequest,
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ExtensionPairingExchangeResponse:
    now = datetime.now(timezone.utc)
    result = await session.execute(
        select(ExtensionPairingCode)
        .where(ExtensionPairingCode.code_hash == _hash_pairing_code(body.code.strip().upper()))
        .with_for_update()
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AuthError("invalid or expired pairing code")
    if row.consumed_at is not None:
        raise AuthError("pairing code already used")
    if row.expires_at <= now:
        raise AuthError("pairing code expired")

    row.consumed_at = now
    _, raw_token = await mint_token(
        user_id=row.user_id,
        name=row.token_name,
        scopes=row.scopes,
        session=session,
    )
    return ExtensionPairingExchangeResponse(
        token=raw_token,
        scopes=list(row.scopes),
        workspace_id=str(row.workspace_id) if row.workspace_id else None,
        api_base_url=row.api_base_url,
        expires_at=row.expires_at,
    )
