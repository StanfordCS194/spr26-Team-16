"""Unit tests for the Supabase JWT verifier (HS256 + ES256/JWKS paths).

DB-free. Self-signs tokens and monkeypatches the JWKS client for the asymmetric path.
"""

from __future__ import annotations

import time
import uuid

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import ec, rsa

from contexthub_backend.api.errors import AuthError
from contexthub_backend.auth import jwt as jwt_module
from contexthub_backend.auth.jwt import make_test_jwt, verify_supabase_jwt

TEST_SECRET = "test-secret-not-for-production-at-least-32-bytes"
TEST_JWKS_URL = "https://example.test/auth/v1/.well-known/jwks.json"


# ---------------------------------------------------------------------------
# HS256 path (used by tests + legacy projects)
# ---------------------------------------------------------------------------


class TestHs256:
    def test_valid_hs256_token_returns_user_id(self):
        uid = uuid.uuid4()
        token = make_test_jwt(uid, TEST_SECRET)
        result = verify_supabase_jwt(token, TEST_SECRET)
        assert result == uid

    def test_hs256_with_no_secret_rejected(self):
        token = make_test_jwt(uuid.uuid4(), TEST_SECRET)
        with pytest.raises(AuthError, match="no shared secret"):
            verify_supabase_jwt(token, None)

    def test_hs256_wrong_secret_rejected(self):
        token = make_test_jwt(uuid.uuid4(), TEST_SECRET)
        with pytest.raises(AuthError):
            verify_supabase_jwt(token, "wrong-secret")

    def test_hs256_expired_rejected(self):
        token = jwt.encode(
            {"sub": str(uuid.uuid4()), "exp": int(time.time()) - 60},
            TEST_SECRET,
            algorithm="HS256",
        )
        with pytest.raises(AuthError):
            verify_supabase_jwt(token, TEST_SECRET)


# ---------------------------------------------------------------------------
# ES256 / RS256 path (Supabase's modern JWKS verification)
# ---------------------------------------------------------------------------


@pytest.fixture
def ec_keypair():
    private_key = ec.generate_private_key(ec.SECP256R1())
    public_key = private_key.public_key()
    return private_key, public_key


@pytest.fixture
def rsa_keypair():
    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()
    return private_key, public_key


def _patch_jwks_with(monkeypatch, public_key) -> None:
    class _StubKey:
        def __init__(self, key):
            self.key = key

    class _StubJWKClient:
        def get_signing_key_from_jwt(self, token):  # noqa: ARG002
            return _StubKey(public_key)

    monkeypatch.setattr(jwt_module, "_get_jwk_client", lambda url: _StubJWKClient())


class TestAsymmetric:
    def test_valid_es256_token_returns_user_id(self, monkeypatch, ec_keypair):
        private_key, public_key = ec_keypair
        _patch_jwks_with(monkeypatch, public_key)

        uid = uuid.uuid4()
        now = int(time.time())
        token = jwt.encode(
            {"sub": str(uid), "iat": now, "exp": now + 3600},
            private_key,
            algorithm="ES256",
            headers={"kid": "test-key-id"},
        )

        assert verify_supabase_jwt(token, secret=None, jwks_url=TEST_JWKS_URL) == uid

    def test_valid_rs256_token_returns_user_id(self, monkeypatch, rsa_keypair):
        private_key, public_key = rsa_keypair
        _patch_jwks_with(monkeypatch, public_key)

        uid = uuid.uuid4()
        now = int(time.time())
        token = jwt.encode(
            {"sub": str(uid), "iat": now, "exp": now + 3600},
            private_key,
            algorithm="RS256",
        )

        assert verify_supabase_jwt(token, secret=None, jwks_url=TEST_JWKS_URL) == uid

    def test_asymmetric_with_no_jwks_url_rejected(self, monkeypatch, ec_keypair):
        private_key, _ = ec_keypair
        token = jwt.encode(
            {"sub": str(uuid.uuid4()), "exp": int(time.time()) + 3600},
            private_key,
            algorithm="ES256",
        )
        with pytest.raises(AuthError, match="no JWKS URL"):
            verify_supabase_jwt(token, secret=None, jwks_url=None)

    def test_asymmetric_signature_mismatch_rejected(self, monkeypatch, ec_keypair):
        # Sign with key A, verify against key B — JWKS stub returns key B.
        rogue, _ = ec_keypair
        _, victim_pub = (ec.generate_private_key(ec.SECP256R1()), None)
        # Generate a separate keypair for the JWKS stub.
        other = ec.generate_private_key(ec.SECP256R1())
        _patch_jwks_with(monkeypatch, other.public_key())

        token = jwt.encode(
            {"sub": str(uuid.uuid4()), "exp": int(time.time()) + 3600},
            rogue,
            algorithm="ES256",
        )
        with pytest.raises(AuthError):
            verify_supabase_jwt(token, secret=None, jwks_url=TEST_JWKS_URL)

    def test_asymmetric_expired_rejected(self, monkeypatch, ec_keypair):
        private_key, public_key = ec_keypair
        _patch_jwks_with(monkeypatch, public_key)

        token = jwt.encode(
            {"sub": str(uuid.uuid4()), "exp": int(time.time()) - 60},
            private_key,
            algorithm="ES256",
        )
        with pytest.raises(AuthError):
            verify_supabase_jwt(token, secret=None, jwks_url=TEST_JWKS_URL)


# ---------------------------------------------------------------------------
# Mixed
# ---------------------------------------------------------------------------


class TestSubClaim:
    def test_sub_must_be_uuid(self, monkeypatch, ec_keypair):
        private_key, public_key = ec_keypair
        _patch_jwks_with(monkeypatch, public_key)

        token = jwt.encode(
            {"sub": "not-a-uuid", "exp": int(time.time()) + 3600},
            private_key,
            algorithm="ES256",
        )
        with pytest.raises(AuthError, match="not a valid UUID"):
            verify_supabase_jwt(token, secret=None, jwks_url=TEST_JWKS_URL)
