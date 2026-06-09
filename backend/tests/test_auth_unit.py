"""Unit tests for auth/jwt.py and auth/tokens.py — no DB or network required."""

from __future__ import annotations

import hashlib
import time
import uuid

import jwt
import pytest

from contexthub_backend.api.errors import AuthError
from contexthub_backend.auth.jwt import make_test_jwt, verify_supabase_jwt
from contexthub_backend.auth.tokens import (
    ALL_SCOPES,
    TOKEN_PREFIX,
    VALID_SCOPES,
    generate_raw_token,
    hash_token,
)

SECRET = "test-secret-unit-at-least-32-bytes-long-for-hs256"


# ---------------------------------------------------------------------------
# JWT verification
# ---------------------------------------------------------------------------


class TestVerifySupabaseJwt:
    def _mint(self, sub: str, exp_offset: int = 3600, extra: dict | None = None) -> str:
        claims = {"sub": sub, "exp": int(time.time()) + exp_offset}
        if extra:
            claims.update(extra)
        return jwt.encode(claims, SECRET, algorithm="HS256")

    def test_valid_jwt_returns_user_id(self):
        uid = uuid.uuid4()
        token = self._mint(str(uid))
        result = verify_supabase_jwt(token, SECRET)
        assert result == uid

    def test_wrong_secret_raises_auth_error(self):
        uid = uuid.uuid4()
        token = self._mint(str(uid))
        with pytest.raises(AuthError, match="invalid JWT"):
            verify_supabase_jwt(token, "wrong-secret")

    def test_expired_token_raises_auth_error(self):
        uid = uuid.uuid4()
        token = self._mint(str(uid), exp_offset=-1)
        with pytest.raises(AuthError, match="invalid JWT"):
            verify_supabase_jwt(token, SECRET)

    def test_missing_sub_raises_auth_error(self):
        token = jwt.encode({"exp": int(time.time()) + 3600}, SECRET, algorithm="HS256")
        with pytest.raises(AuthError):
            verify_supabase_jwt(token, SECRET)

    def test_non_uuid_sub_raises_auth_error(self):
        token = self._mint("not-a-uuid")
        with pytest.raises(AuthError, match="not a valid UUID"):
            verify_supabase_jwt(token, SECRET)

    def test_wrong_algorithm_rejected(self):
        uid = uuid.uuid4()
        # RS256 token presented to HS256-only verifier
        with pytest.raises(AuthError):
            verify_supabase_jwt("header.payload.sig", SECRET)

    def test_make_test_jwt_roundtrip(self):
        uid = uuid.uuid4()
        token = make_test_jwt(uid, SECRET)
        result = verify_supabase_jwt(token, SECRET)
        assert result == uid

    def test_make_test_jwt_extra_claims(self):
        uid = uuid.uuid4()
        token = make_test_jwt(uid, SECRET, extra={"role": "authenticated"})
        payload = jwt.decode(token, SECRET, algorithms=["HS256"])
        assert payload["role"] == "authenticated"


# ---------------------------------------------------------------------------
# Token generation and hashing
# ---------------------------------------------------------------------------


class TestGenerateRawToken:
    def test_prefix(self):
        t = generate_raw_token()
        assert t.startswith(TOKEN_PREFIX)

    def test_length(self):
        # "ch_" + 64 hex chars = 67
        t = generate_raw_token()
        assert len(t) == 67

    def test_unique(self):
        tokens = {generate_raw_token() for _ in range(200)}
        assert len(tokens) == 200

    def test_hex_body(self):
        t = generate_raw_token()
        body = t[len(TOKEN_PREFIX):]
        assert all(c in "0123456789abcdef" for c in body)


class TestHashToken:
    def test_deterministic(self):
        raw = "ch_" + "a" * 64
        assert hash_token(raw) == hash_token(raw)

    def test_sha256_length(self):
        assert len(hash_token(generate_raw_token())) == 64

    def test_matches_stdlib(self):
        raw = generate_raw_token()
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert hash_token(raw) == expected

    def test_different_tokens_different_hashes(self):
        hashes = {hash_token(generate_raw_token()) for _ in range(100)}
        assert len(hashes) == 100


# ---------------------------------------------------------------------------
# Scope constants
# ---------------------------------------------------------------------------


class TestScopeConstants:
    def test_all_scopes_subset_of_valid(self):
        assert set(ALL_SCOPES) == VALID_SCOPES

    def test_valid_scopes_has_four_entries(self):
        assert len(VALID_SCOPES) == 4

    def test_expected_scope_names(self):
        assert VALID_SCOPES == {"push", "pull", "search", "read"}
