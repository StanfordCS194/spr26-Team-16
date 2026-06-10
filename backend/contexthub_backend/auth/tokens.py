"""API token mint / verify / revoke.

Token format: ch_<64 hex chars>  (prefix + secrets.token_hex(32))
Storage: SHA-256 hash of the full raw token string.
Scopes (v0): push, pull, search, read.
"""

import hashlib
import secrets
import uuid
from datetime import datetime, timezone

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.api.errors import AuthError, ForbiddenError, NotFoundError
from contexthub_backend.db.models import ApiToken
from contexthub_backend.db.short_id import uuid7

TOKEN_PREFIX = "ch_"
VALID_SCOPES: frozenset[str] = frozenset({"push", "pull", "search", "read"})
ALL_SCOPES: list[str] = ["push", "pull", "search", "read"]


def hash_token(raw: str) -> str:
    return hashlib.sha256(raw.encode()).hexdigest()


def generate_raw_token() -> str:
    return TOKEN_PREFIX + secrets.token_hex(32)


async def mint_token(
    user_id: uuid.UUID,
    name: str,
    scopes: list[str],
    session: AsyncSession,
) -> tuple[ApiToken, str]:
    """Create a new API token row. Returns (row, raw_token); raw_token shown once."""
    invalid = set(scopes) - VALID_SCOPES
    if invalid:
        raise ValueError(f"invalid scopes: {sorted(invalid)}")

    raw = generate_raw_token()
    row = ApiToken(
        id=uuid7(),
        user_id=user_id,
        name=name,
        token_hash=hash_token(raw),
        scopes=scopes,
    )
    session.add(row)
    await session.flush()
    return row, raw


async def verify_api_token(raw: str, session: AsyncSession) -> ApiToken:
    """Look up a raw token by hash. Raises AuthError if missing or revoked.

    Called before RLS context is set — uses the superuser connection to see
    all token rows regardless of user ownership.
    """
    result = await session.execute(
        select(ApiToken).where(
            ApiToken.token_hash == hash_token(raw),
            ApiToken.revoked_at.is_(None),
        )
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise AuthError("invalid or revoked API token")
    return row


async def touch_token(row: ApiToken) -> None:
    """Update last_used_at in-place; will be flushed with the session commit."""
    row.last_used_at = datetime.now(timezone.utc)


async def revoke_token(
    token_id: uuid.UUID,
    requesting_user_id: uuid.UUID,
    session: AsyncSession,
) -> ApiToken:
    """Mark a token revoked. Raises NotFoundError if not found, ForbiddenError if not owner."""
    result = await session.execute(
        select(ApiToken).where(ApiToken.id == token_id)
    )
    row = result.scalar_one_or_none()
    if row is None:
        raise NotFoundError("token not found")
    if row.user_id != requesting_user_id:
        raise ForbiddenError("cannot revoke another user's token")
    if row.revoked_at is not None:
        raise NotFoundError("token already revoked")
    row.revoked_at = datetime.now(timezone.utc)
    await session.flush()
    return row
