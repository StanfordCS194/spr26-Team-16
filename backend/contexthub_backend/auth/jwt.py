"""Supabase JWT verification.

Supabase started signing project JWTs with asymmetric keys (ES256/RS256) in 2024.
We resolve the signing key from the project's JWKS endpoint:

    https://<project>.supabase.co/auth/v1/.well-known/jwks.json

PyJWKClient caches keys in-process and re-fetches when an unknown `kid` arrives,
so key rotation is handled automatically.

For backwards compatibility (and for tests), if `supabase_jwt_secret` is configured
and the token is HS256, we fall back to symmetric verification.
"""

from __future__ import annotations

import threading
import time
import uuid

import jwt
from jwt import PyJWKClient, PyJWTError

from contexthub_backend.api.errors import AuthError

_JWK_CACHE_LOCK = threading.Lock()
_jwk_clients: dict[str, tuple[PyJWKClient, float]] = {}
_JWK_CLIENT_TTL_SECONDS = 3600.0


def _get_jwk_client(jwks_url: str) -> PyJWKClient:
    with _JWK_CACHE_LOCK:
        cached = _jwk_clients.get(jwks_url)
        now = time.time()
        if cached is None or (now - cached[1]) > _JWK_CLIENT_TTL_SECONDS:
            client = PyJWKClient(jwks_url, cache_keys=True, lifespan=_JWK_CLIENT_TTL_SECONDS)
            _jwk_clients[jwks_url] = (client, now)
            return client
        return cached[0]


def _is_unsigned_or_symmetric(token: str) -> bool:
    """Cheap check: peek at the unverified header to pick a verification path."""
    try:
        header = jwt.get_unverified_header(token)
    except PyJWTError:
        return False
    return str(header.get("alg", "")).startswith("HS")


def verify_supabase_jwt(
    token: str,
    secret: str | None = None,
    *,
    jwks_url: str | None = None,
) -> uuid.UUID:
    """Verify a Supabase JWT and return the user_id (sub claim).

    Asymmetric tokens (ES256/RS256) are verified against the JWKS endpoint.
    Symmetric tokens (HS256) fall back to the shared secret for tests / legacy projects.
    """
    if _is_unsigned_or_symmetric(token):
        if not secret:
            raise AuthError("HS256 token presented but no shared secret configured")
        try:
            payload = jwt.decode(
                token,
                secret,
                algorithms=["HS256"],
                options={"require": ["sub", "exp"]},
            )
        except PyJWTError as exc:
            raise AuthError(f"invalid JWT: {exc}") from exc
    else:
        if not jwks_url:
            raise AuthError("asymmetric JWT presented but no JWKS URL configured")
        try:
            signing_key = _get_jwk_client(jwks_url).get_signing_key_from_jwt(token)
        except PyJWTError as exc:
            raise AuthError(f"could not resolve Supabase signing key: {exc}") from exc
        except Exception as exc:
            raise AuthError(f"could not fetch Supabase JWKS: {exc}") from exc
        try:
            payload = jwt.decode(
                token,
                signing_key.key,
                algorithms=["ES256", "RS256"],
                options={"require": ["sub", "exp"], "verify_aud": False},
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
    """Generate a signed HS256 JWT for tests. Not for production use."""
    import time as _time

    claims = {
        "sub": str(user_id),
        "role": "authenticated",
        "exp": int(_time.time()) + 3600,
        "iat": int(_time.time()),
    }
    if extra:
        claims.update(extra)
    return jwt.encode(claims, secret, algorithm="HS256")
