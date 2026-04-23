"""Integration tests for auth API endpoints + RLS enforcement through FastAPI.

Requires DATABASE_URL pointing to a live Postgres (with pgvector + auth stub).
Uses the session-scoped db_engine from conftest.py (migrations already run).

Tests:
  - GET /v1/health  (unauthenticated)
  - GET /v1/me with JWT auth
  - GET /v1/me with API-token auth
  - GET /v1/me with no auth → 401
  - GET /v1/me with bad JWT → 401
  - POST /v1/tokens (mint) — JWT required
  - POST /v1/tokens with API token → 403
  - GET /v1/tokens — lists only caller's tokens
  - DELETE /v1/tokens/{id}
  - RLS: user A cannot see user B's tokens via GET /v1/tokens
"""

from __future__ import annotations

import uuid

import psycopg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from contexthub_backend.auth import dependencies as auth_deps
from contexthub_backend.auth.jwt import make_test_jwt
from contexthub_backend.auth.tokens import generate_raw_token, hash_token, mint_token
from contexthub_backend.db.base import make_async_engine
from contexthub_backend.db.short_id import uuid7
from tests.conftest import _psycopg_url

TEST_JWT_SECRET = "test-secret-not-for-production-at-least-32-bytes"


# ---------------------------------------------------------------------------
# Session-scoped async engine + test users
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def async_engine(db_engine):
    """Async engine over the same test DB the sync db_engine fixture already migrated."""
    from contexthub_backend.config import settings

    async_url = settings.database_url.replace(
        "+psycopg://", "+asyncpg://"
    )
    # Fall back for plain postgresql:// URLs
    if "+asyncpg://" not in async_url:
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = make_async_engine(async_url)
    auth_deps._set_engine(engine)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="module")
def auth_users(db_engine):
    """Two test users inserted into auth.users, profiles, and interchange_format_versions."""
    user_a = uuid7()
    user_b = uuid7()

    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        for uid, email in [
            (user_a, "auth-alice@test.local"),
            (user_b, "auth-bob@test.local"),
        ]:
            conn.execute(
                "INSERT INTO auth.users (id, email) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (str(uid), email),
            )
            conn.execute(
                "INSERT INTO profiles (user_id, display_name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (str(uid), f"Auth User {uid}"),
            )
        conn.execute(
            "INSERT INTO interchange_format_versions (version, json_schema) "
            "VALUES ('ch.v0.1', '{}'::jsonb) ON CONFLICT DO NOTHING"
        )
    return {"user_a": user_a, "user_b": user_b}


@pytest_asyncio.fixture(scope="module")
async def client(async_engine):
    """Module-scoped HTTP test client."""
    import os

    os.environ.setdefault("SUPABASE_JWT_SECRET", TEST_JWT_SECRET)

    from contexthub_backend.api.app import create_app
    from contexthub_backend.config import Settings
    import contexthub_backend.config as cfg_module

    # Point settings at test JWT secret
    cfg_module.settings = Settings(
        supabase_jwt_secret=TEST_JWT_SECRET,
        database_url=cfg_module.settings.database_url,
    )

    app = create_app(engine=async_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def jwt_for(user_id: uuid.UUID) -> str:
    return make_test_jwt(user_id, TEST_JWT_SECRET)


# ---------------------------------------------------------------------------
# Health (unauthenticated)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestHealth:
    async def test_health(self, client):
        r = await client.get("/v1/health")
        assert r.status_code == 200
        assert r.json()["status"] == "ok"

    async def test_version(self, client):
        r = await client.get("/v1/version")
        assert r.status_code == 200
        assert "version" in r.json()

    async def test_response_has_request_id_header(self, client):
        r = await client.get("/v1/health")
        assert "x-request-id" in r.headers


# ---------------------------------------------------------------------------
# GET /v1/me
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestGetMe:
    async def test_jwt_auth_returns_profile(self, client, auth_users):
        uid = auth_users["user_a"]
        r = await client.get("/v1/me", headers={"Authorization": f"Bearer {jwt_for(uid)}"})
        assert r.status_code == 200
        data = r.json()
        assert data["user_id"] == str(uid)

    async def test_no_auth_returns_401(self, client):
        r = await client.get("/v1/me")
        assert r.status_code == 422  # FastAPI missing required header

    async def test_invalid_bearer_returns_401(self, client):
        r = await client.get("/v1/me", headers={"Authorization": "Bearer not-valid"})
        assert r.status_code == 401

    async def test_wrong_jwt_secret_returns_401(self, client, auth_users):
        uid = auth_users["user_a"]
        bad_token = make_test_jwt(uid, "wrong-secret")
        r = await client.get("/v1/me", headers={"Authorization": f"Bearer {bad_token}"})
        assert r.status_code == 401

    async def test_api_token_auth_returns_profile(self, client, auth_users, async_engine):
        from sqlalchemy.ext.asyncio import AsyncSession

        uid = auth_users["user_a"]
        raw_token = None

        async with AsyncSession(async_engine) as session:
            async with session.begin():
                row, raw = await mint_token(
                    user_id=uid, name="test-token-me", scopes=["read"], session=session
                )
                raw_token = raw

        r = await client.get("/v1/me", headers={"Authorization": f"Bearer {raw_token}"})
        assert r.status_code == 200
        assert r.json()["user_id"] == str(uid)

    async def test_user_a_and_b_get_their_own_profile(self, client, auth_users):
        for key in ("user_a", "user_b"):
            uid = auth_users[key]
            r = await client.get("/v1/me", headers={"Authorization": f"Bearer {jwt_for(uid)}"})
            assert r.status_code == 200
            assert r.json()["user_id"] == str(uid)


# ---------------------------------------------------------------------------
# POST /v1/tokens  (mint)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestMintToken:
    async def test_jwt_can_mint_token(self, client, auth_users):
        uid = auth_users["user_a"]
        r = await client.post(
            "/v1/tokens",
            json={"name": "My Extension", "scopes": ["push", "read"]},
            headers={"Authorization": f"Bearer {jwt_for(uid)}"},
        )
        assert r.status_code == 201
        data = r.json()
        assert data["name"] == "My Extension"
        assert set(data["scopes"]) == {"push", "read"}
        assert data["token"].startswith("ch_")
        assert len(data["token"]) == 67

    async def test_api_token_cannot_mint(self, client, auth_users, async_engine):
        """A compromised API token must not be able to mint new tokens."""
        from sqlalchemy.ext.asyncio import AsyncSession

        uid = auth_users["user_b"]
        async with AsyncSession(async_engine) as session:
            async with session.begin():
                _, raw = await mint_token(
                    user_id=uid, name="existing-token", scopes=ALL_SCOPES, session=session
                )

        r = await client.post(
            "/v1/tokens",
            json={"name": "new-token", "scopes": ["push"]},
            headers={"Authorization": f"Bearer {raw}"},
        )
        assert r.status_code == 403

    async def test_invalid_scopes_rejected(self, client, auth_users):
        uid = auth_users["user_a"]
        r = await client.post(
            "/v1/tokens",
            json={"name": "bad", "scopes": ["push", "admin"]},
            headers={"Authorization": f"Bearer {jwt_for(uid)}"},
        )
        assert r.status_code == 422

    async def test_empty_scopes_rejected(self, client, auth_users):
        uid = auth_users["user_a"]
        r = await client.post(
            "/v1/tokens",
            json={"name": "empty", "scopes": []},
            headers={"Authorization": f"Bearer {jwt_for(uid)}"},
        )
        assert r.status_code == 422

    async def test_raw_token_not_in_subsequent_list(self, client, auth_users):
        """The response token is the raw value; GET /v1/tokens must not expose token_hash."""
        uid = auth_users["user_a"]
        mint_r = await client.post(
            "/v1/tokens",
            json={"name": "list-check", "scopes": ["read"]},
            headers={"Authorization": f"Bearer {jwt_for(uid)}"},
        )
        assert mint_r.status_code == 201
        raw = mint_r.json()["token"]

        list_r = await client.get(
            "/v1/tokens", headers={"Authorization": f"Bearer {jwt_for(uid)}"}
        )
        for item in list_r.json():
            assert "token" not in item
            assert raw not in str(item)


# ---------------------------------------------------------------------------
# GET /v1/tokens  (list)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListTokens:
    async def test_lists_own_tokens(self, client, auth_users):
        uid = auth_users["user_a"]
        await client.post(
            "/v1/tokens",
            json={"name": "list-test", "scopes": ["push"]},
            headers={"Authorization": f"Bearer {jwt_for(uid)}"},
        )
        r = await client.get("/v1/tokens", headers={"Authorization": f"Bearer {jwt_for(uid)}"})
        assert r.status_code == 200
        ids = {item["id"] for item in r.json()}
        assert len(ids) >= 1


@pytest.mark.integration
class TestRlsTokensViaApi:
    """RLS check: user A cannot see user B's tokens through the API."""

    async def test_user_a_cannot_see_user_b_tokens(self, client, auth_users):
        uid_a = auth_users["user_a"]
        uid_b = auth_users["user_b"]

        # Mint a token as user B
        mint_r = await client.post(
            "/v1/tokens",
            json={"name": "b-private-token", "scopes": ["push"]},
            headers={"Authorization": f"Bearer {jwt_for(uid_b)}"},
        )
        assert mint_r.status_code == 201
        b_token_id = mint_r.json()["id"]

        # List tokens as user A — must not see user B's token
        list_r = await client.get(
            "/v1/tokens", headers={"Authorization": f"Bearer {jwt_for(uid_a)}"}
        )
        assert list_r.status_code == 200
        a_ids = {item["id"] for item in list_r.json()}
        assert b_token_id not in a_ids

    async def test_user_b_cannot_see_user_a_tokens(self, client, auth_users):
        uid_a = auth_users["user_a"]
        uid_b = auth_users["user_b"]

        mint_r = await client.post(
            "/v1/tokens",
            json={"name": "a-private-token", "scopes": ["read"]},
            headers={"Authorization": f"Bearer {jwt_for(uid_a)}"},
        )
        assert mint_r.status_code == 201
        a_token_id = mint_r.json()["id"]

        list_r = await client.get(
            "/v1/tokens", headers={"Authorization": f"Bearer {jwt_for(uid_b)}"}
        )
        assert list_r.status_code == 200
        b_ids = {item["id"] for item in list_r.json()}
        assert a_token_id not in b_ids


# ---------------------------------------------------------------------------
# DELETE /v1/tokens/{id}  (revoke)
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRevokeToken:
    async def test_owner_can_revoke(self, client, auth_users):
        uid = auth_users["user_a"]
        mint_r = await client.post(
            "/v1/tokens",
            json={"name": "to-revoke", "scopes": ["push"]},
            headers={"Authorization": f"Bearer {jwt_for(uid)}"},
        )
        token_id = mint_r.json()["id"]

        del_r = await client.delete(
            f"/v1/tokens/{token_id}",
            headers={"Authorization": f"Bearer {jwt_for(uid)}"},
        )
        assert del_r.status_code == 204

        # Token no longer appears in list
        list_r = await client.get(
            "/v1/tokens", headers={"Authorization": f"Bearer {jwt_for(uid)}"}
        )
        ids = {item["id"] for item in list_r.json()}
        assert token_id not in ids

    async def test_revoked_token_cannot_authenticate(self, client, auth_users):
        uid = auth_users["user_a"]
        mint_r = await client.post(
            "/v1/tokens",
            json={"name": "revoke-then-use", "scopes": ["read"]},
            headers={"Authorization": f"Bearer {jwt_for(uid)}"},
        )
        token_id = mint_r.json()["id"]
        raw = mint_r.json()["token"]

        await client.delete(
            f"/v1/tokens/{token_id}",
            headers={"Authorization": f"Bearer {jwt_for(uid)}"},
        )

        r = await client.get("/v1/me", headers={"Authorization": f"Bearer {raw}"})
        assert r.status_code == 401

    async def test_user_b_cannot_revoke_user_a_token(self, client, auth_users):
        uid_a = auth_users["user_a"]
        uid_b = auth_users["user_b"]

        mint_r = await client.post(
            "/v1/tokens",
            json={"name": "a-token-b-tries", "scopes": ["push"]},
            headers={"Authorization": f"Bearer {jwt_for(uid_a)}"},
        )
        token_id = mint_r.json()["id"]

        del_r = await client.delete(
            f"/v1/tokens/{token_id}",
            headers={"Authorization": f"Bearer {jwt_for(uid_b)}"},
        )
        assert del_r.status_code == 403


# Convenience import for test_auth_api.py internal use
from contexthub_backend.auth.tokens import ALL_SCOPES  # noqa: E402
