"""FastAPI dependency providers for authentication and DB session management.

Dependency chain per authenticated request:

  get_db_session          — opens a transaction (superuser connection, no RLS yet)
       │
  get_current_user        — resolves identity from JWT or ch_ token using that session
       │
  get_rls_session         — sets SET LOCAL ROLE + app.current_user_id on the same
                            transaction so all subsequent queries obey RLS
       │
  route handler           — receives (user, rls_session); RLS enforced automatically

The token lookup in get_current_user intentionally runs before RLS is applied:
the superuser connection can see all api_tokens rows to identify the caller.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Annotated, AsyncGenerator

from fastapi import Depends, Header
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession

from contexthub_backend.api.errors import AuthError, ForbiddenError
from contexthub_backend.auth.jwt import verify_supabase_jwt
from contexthub_backend.auth.tokens import ALL_SCOPES, touch_token, verify_api_token
from contexthub_backend.config import settings
from contexthub_backend.db.base import make_async_engine

# Module-level engine singleton — override via _set_engine() in tests.
_engine: AsyncEngine | None = None


def _get_engine() -> AsyncEngine:
    global _engine
    if _engine is None:
        _engine = make_async_engine(settings.async_database_url)
    return _engine


def _set_engine(engine: AsyncEngine) -> None:
    """Inject a test engine; call before the first request in test suites."""
    global _engine
    _engine = engine


# ---------------------------------------------------------------------------
# Typed user principal
# ---------------------------------------------------------------------------

@dataclass
class AuthUser:
    user_id: uuid.UUID
    scopes: list[str]
    auth_type: str  # "jwt" | "api_token"

    def has_scope(self, scope: str) -> bool:
        return scope in self.scopes

    def require_scope(self, scope: str) -> None:
        if not self.has_scope(scope):
            raise ForbiddenError(f"token missing required scope: {scope}")


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _extract_bearer(authorization: str) -> str:
    if not authorization.startswith("Bearer "):
        raise AuthError("Authorization header must be 'Bearer <token>'")
    return authorization[len("Bearer "):]


def _is_jwt(token: str) -> bool:
    return token.count(".") == 2


# ---------------------------------------------------------------------------
# Core dependencies
# ---------------------------------------------------------------------------

async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Open a transaction on the superuser connection (no RLS applied yet)."""
    async with AsyncSession(_get_engine()) as session:
        async with session.begin():
            yield session


async def get_current_user(
    authorization: Annotated[str, Header()],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuthUser:
    """Resolve the caller's identity from the Authorization header.

    Accepts:
      - Supabase JWT  → verified with HS256 + SUPABASE_JWT_SECRET
      - ch_ API token → looked up by SHA-256 hash in api_tokens
    """
    token = _extract_bearer(authorization)

    if _is_jwt(token):
        user_id = verify_supabase_jwt(token, settings.supabase_jwt_secret)
        return AuthUser(user_id=user_id, scopes=list(ALL_SCOPES), auth_type="jwt")

    if token.startswith("ch_"):
        row = await verify_api_token(token, session)
        await touch_token(row)
        return AuthUser(user_id=row.user_id, scopes=list(row.scopes), auth_type="api_token")

    raise AuthError("unrecognised token format")


async def get_rls_session(
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AsyncSession:
    """Apply RLS context to the open transaction and return the session.

    After this point every query runs as ch_authenticated with auth.uid()
    returning the authenticated user's UUID.
    """
    await session.execute(text("SET LOCAL ROLE ch_authenticated"))
    await session.execute(
        text("SELECT set_config('app.current_user_id', :uid, true)"),
        {"uid": str(user.user_id)},
    )
    return session


def require_jwt(user: Annotated[AuthUser, Depends(get_current_user)]) -> AuthUser:
    """Guard that only allows Supabase JWT callers (not API tokens).

    Used on token-mint endpoint: a compromised API token must not be able
    to mint new tokens with elevated scopes.
    """
    if user.auth_type != "jwt":
        raise ForbiddenError("this endpoint requires Supabase JWT authentication")
    return user
