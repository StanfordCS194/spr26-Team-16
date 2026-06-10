"""Google ID token verification.

Verifies a Google-issued OIDC ID token (RS256) using Google's JWKS.
Used by POST /v1/auth/google to exchange a Google sign-in for a ch_ API token.

Security notes:
  - Verifies signature against Google's published JWKS (auto-rotates).
  - Validates `aud` against configured client IDs (one per app: extension, dashboard).
  - Validates `iss` is `accounts.google.com` or `https://accounts.google.com`.
  - Enforces `exp` and `iat` (PyJWT does this).
  - Caches JWKS in-process for 1h to avoid hammering Google.
"""

from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass

import httpx
import jwt
from jwt import PyJWKClient, PyJWTError

from contexthub_backend.api.errors import AuthError

GOOGLE_JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"
GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})

# Stable namespace for deriving deterministic UUIDs from Google `sub` claims.
# Generated once; never change — changing it would orphan every existing user.
_GOOGLE_SUB_NAMESPACE = uuid.UUID("3a0e4b2f-9c1a-4f6d-8a12-c4e2b8f7d61a")


@dataclass(frozen=True)
class GoogleIdentity:
    user_id: uuid.UUID  # deterministic UUID5 derived from Google `sub`
    email: str
    email_verified: bool
    name: str | None
    picture: str | None
    google_sub: str


# ---------------------------------------------------------------------------
# JWKS client (PyJWKClient handles caching internally)
# ---------------------------------------------------------------------------

_jwk_lock = threading.Lock()
_jwk_client: PyJWKClient | None = None
_jwk_client_created_at: float = 0.0
_JWK_CLIENT_TTL_SECONDS = 3600.0


def _get_jwk_client() -> PyJWKClient:
    """Return a process-wide JWKS client, rebuilding it hourly so key rotation is picked up."""
    global _jwk_client, _jwk_client_created_at
    with _jwk_lock:
        now = time.time()
        if _jwk_client is None or (now - _jwk_client_created_at) > _JWK_CLIENT_TTL_SECONDS:
            _jwk_client = PyJWKClient(GOOGLE_JWKS_URL, cache_keys=True, lifespan=_JWK_CLIENT_TTL_SECONDS)
            _jwk_client_created_at = now
        return _jwk_client


def _parse_client_ids(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def derive_user_id(google_sub: str) -> uuid.UUID:
    """Map a Google `sub` claim to a stable internal UUID.

    Same Google account always produces the same user_id, across machines and
    re-installs — this is what lets a user sign in on a new device and see
    all their existing data.
    """
    return uuid.uuid5(_GOOGLE_SUB_NAMESPACE, google_sub)


def verify_google_id_token(id_token: str, allowed_audiences: list[str]) -> GoogleIdentity:
    """Verify a Google-issued OIDC ID token. Returns identity claims.

    Raises AuthError on any verification failure — caller maps to 401.
    """
    if not allowed_audiences:
        raise AuthError("Google sign-in is not configured on this server")

    try:
        signing_key = _get_jwk_client().get_signing_key_from_jwt(id_token)
    except PyJWTError as exc:
        raise AuthError(f"could not resolve Google signing key: {exc}") from exc
    except httpx.HTTPError as exc:
        raise AuthError(f"could not fetch Google JWKS: {exc}") from exc
    except Exception as exc:  # urllib errors from PyJWKClient
        raise AuthError(f"could not fetch Google JWKS: {exc}") from exc

    try:
        payload = jwt.decode(
            id_token,
            signing_key.key,
            algorithms=["RS256"],
            audience=allowed_audiences,
            options={"require": ["sub", "exp", "iat", "iss", "aud"]},
        )
    except PyJWTError as exc:
        raise AuthError(f"invalid Google ID token: {exc}") from exc

    iss = payload.get("iss")
    if iss not in GOOGLE_ISSUERS:
        raise AuthError(f"unexpected ID token issuer: {iss}")

    sub = payload.get("sub")
    email = payload.get("email")
    if not sub or not email:
        raise AuthError("Google ID token missing sub or email")

    return GoogleIdentity(
        user_id=derive_user_id(str(sub)),
        email=str(email),
        email_verified=bool(payload.get("email_verified", False)),
        name=payload.get("name") or None,
        picture=payload.get("picture") or None,
        google_sub=str(sub),
    )


def configured_client_ids(raw_setting: str) -> list[str]:
    """Public wrapper so the route can advertise whether Google sign-in is on."""
    return _parse_client_ids(raw_setting)
