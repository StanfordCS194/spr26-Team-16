"""Unit tests for the Google ID token verifier.

DB-free. Self-signs RSA test keys and monkeypatches PyJWKClient so the
verification code path is exercised end-to-end without hitting Google.
"""

from __future__ import annotations

import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from contexthub_backend.api.errors import AuthError
from contexthub_backend.auth import google as google_auth_module
from contexthub_backend.auth.google import (
    derive_user_id,
    verify_google_id_token,
)


# ---------------------------------------------------------------------------
# Test key + JWKS monkeypatch
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture(autouse=True)
def patch_jwks(monkeypatch, rsa_keypair):
    """Replace the real PyJWKClient with a stub that returns our test public key."""
    _, public_key = rsa_keypair

    class _StubSigningKey:
        def __init__(self, key):
            self.key = key

    class _StubJWKClient:
        def get_signing_key_from_jwt(self, token):  # noqa: ARG002
            return _StubSigningKey(public_key)

    monkeypatch.setattr(google_auth_module, "_get_jwk_client", lambda: _StubJWKClient())
    yield


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _mint_id_token(
    private_key,
    *,
    sub: str = "1234567890",
    email: str = "alice@example.com",
    aud: str = "test-client.apps.googleusercontent.com",
    iss: str = "https://accounts.google.com",
    name: str | None = "Alice Tester",
    picture: str | None = "https://lh3.googleusercontent.com/a/test",
    email_verified: bool = True,
    exp_offset: int = 3600,
    extra_claims: dict | None = None,
) -> str:
    now = int(time.time())
    claims = {
        "iss": iss,
        "sub": sub,
        "aud": aud,
        "email": email,
        "email_verified": email_verified,
        "name": name,
        "picture": picture,
        "iat": now,
        "exp": now + exp_offset,
    }
    if extra_claims:
        claims.update(extra_claims)
    return jwt.encode(claims, private_key, algorithm="RS256")


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------


class TestVerifyGoogleIdTokenHappyPath:
    def test_returns_identity_for_valid_token(self, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _mint_id_token(private_key)

        identity = verify_google_id_token(token, ["test-client.apps.googleusercontent.com"])

        assert identity.email == "alice@example.com"
        assert identity.email_verified is True
        assert identity.name == "Alice Tester"
        assert identity.picture == "https://lh3.googleusercontent.com/a/test"
        assert identity.google_sub == "1234567890"
        assert identity.user_id == derive_user_id("1234567890")
        assert isinstance(identity.user_id, uuid.UUID)

    def test_accepts_short_form_issuer(self, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _mint_id_token(private_key, iss="accounts.google.com")
        identity = verify_google_id_token(token, ["test-client.apps.googleusercontent.com"])
        assert identity.email == "alice@example.com"

    def test_user_id_is_deterministic_per_sub(self):
        a = derive_user_id("1234567890")
        b = derive_user_id("1234567890")
        c = derive_user_id("1234567891")
        assert a == b
        assert a != c

    def test_accepts_multiple_audiences(self, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _mint_id_token(private_key, aud="dashboard-client.apps.googleusercontent.com")
        identity = verify_google_id_token(
            token,
            [
                "extension-client.apps.googleusercontent.com",
                "dashboard-client.apps.googleusercontent.com",
            ],
        )
        assert identity.email == "alice@example.com"


# ---------------------------------------------------------------------------
# Failure paths
# ---------------------------------------------------------------------------


class TestVerifyGoogleIdTokenFailures:
    def test_no_configured_audiences_rejects(self, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _mint_id_token(private_key)
        with pytest.raises(AuthError, match="not configured"):
            verify_google_id_token(token, [])

    def test_wrong_audience_rejected(self, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _mint_id_token(private_key, aud="someone-else.apps.googleusercontent.com")
        with pytest.raises(AuthError):
            verify_google_id_token(token, ["test-client.apps.googleusercontent.com"])

    def test_wrong_issuer_rejected(self, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _mint_id_token(private_key, iss="https://attacker.example/")
        with pytest.raises(AuthError, match="issuer"):
            verify_google_id_token(token, ["test-client.apps.googleusercontent.com"])

    def test_expired_token_rejected(self, rsa_keypair):
        private_key, _ = rsa_keypair
        token = _mint_id_token(private_key, exp_offset=-60)
        with pytest.raises(AuthError):
            verify_google_id_token(token, ["test-client.apps.googleusercontent.com"])

    def test_token_missing_email_rejected(self, rsa_keypair):
        private_key, _ = rsa_keypair
        # Build a token without `email` by constructing claims manually.
        now = int(time.time())
        claims = {
            "iss": "https://accounts.google.com",
            "sub": "1234567890",
            "aud": "test-client.apps.googleusercontent.com",
            "iat": now,
            "exp": now + 3600,
        }
        token = jwt.encode(claims, private_key, algorithm="RS256")
        with pytest.raises(AuthError, match="missing"):
            verify_google_id_token(token, ["test-client.apps.googleusercontent.com"])

    def test_garbage_token_rejected(self):
        with pytest.raises(AuthError):
            verify_google_id_token(
                "not-a-jwt", ["test-client.apps.googleusercontent.com"]
            )

    def test_signature_mismatch_rejected(self, rsa_keypair):
        # Sign with a different key than the JWKS stub returns.
        rogue_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        token = _mint_id_token(rogue_key)
        with pytest.raises(AuthError):
            verify_google_id_token(token, ["test-client.apps.googleusercontent.com"])
