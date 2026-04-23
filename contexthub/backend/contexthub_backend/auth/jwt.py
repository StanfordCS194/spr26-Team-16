"""Supabase JWT verification.

Supabase JWTs are HS256, signed with SUPABASE_JWT_SECRET.
Claims: sub (user UUID), role, exp, iat, email.
"""

import uuid

import jwt
from jwt import PyJWTError

from contexthub_backend.api.errors import AuthError


def verify_supabase_jwt(token: str, secret: str) -> uuid.UUID:
    """Verify a Supabase HS256 JWT and return the user_id (sub claim)."""
    try:
        payload = jwt.decode(
            token,
            secret,
            algorithms=["HS256"],
            options={"require": ["sub", "exp"]},
        )
    except PyJWTError as exc:
        raise AuthError(f"invalid JWT: {exc}") from exc

    sub = payload.get("sub")
    if not sub:
        raise AuthError("JWT missing sub claim")

    try:
        return uuid.UUID(sub)
    except ValueError as exc:
        raise AuthError("JWT sub is not a valid UUID") from exc


def make_test_jwt(user_id: uuid.UUID, secret: str, extra: dict | None = None) -> str:
    """Generate a signed JWT for tests. Not for production use."""
    import time

    claims = {
        "sub": str(user_id),
        "role": "authenticated",
        "exp": int(time.time()) + 3600,
        "iat": int(time.time()),
    }
    if extra:
        claims.update(extra)
    return jwt.encode(claims, secret, algorithm="HS256")
