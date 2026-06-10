"""Integration tests for POST /v1/auth/google.

Requires a live Postgres + pgvector + auth stub (see conftest.py db_engine).
Run with `pytest -m integration` once a DB is up.

These tests stub out Google's JWKS so we don't need network access — they
verify the *full server-side flow*: token verify → upsert auth.users + profile
→ create workspace → mint ch_ token → return.
"""

from __future__ import annotations

import time

import jwt
import pytest
import pytest_asyncio
from cryptography.hazmat.primitives.asymmetric import rsa
from httpx import ASGITransport, AsyncClient

from contexthub_backend.auth import dependencies as auth_deps
from contexthub_backend.auth import google as google_auth_module
from contexthub_backend.db.base import make_async_engine

TEST_AUDIENCE = "test-extension.apps.googleusercontent.com"


@pytest_asyncio.fixture(scope="module")
async def google_async_engine(db_engine):
    from contexthub_backend.config import settings

    async_url = settings.database_url.replace("+psycopg://", "+asyncpg://")
    if "+asyncpg://" not in async_url:
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)
    engine = make_async_engine(async_url)
    auth_deps._set_engine(engine)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="module")
async def google_client(google_async_engine, monkeypatch_module):
    """Test client with Google JWKS stubbed and one allowed audience configured."""
    import contexthub_backend.config as cfg_module

    cfg_module.settings.google_oauth_client_ids = TEST_AUDIENCE

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    public_key = private_key.public_key()

    class _StubKey:
        def __init__(self, key):
            self.key = key

    class _StubJWKClient:
        def get_signing_key_from_jwt(self, token):  # noqa: ARG002
            return _StubKey(public_key)

    monkeypatch_module.setattr(google_auth_module, "_get_jwk_client", lambda: _StubJWKClient())

    from contexthub_backend.api.app import create_app

    app = create_app(engine=google_async_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c, private_key


@pytest.fixture(scope="module")
def monkeypatch_module():
    from _pytest.monkeypatch import MonkeyPatch

    mp = MonkeyPatch()
    yield mp
    mp.undo()


def _mint_id_token(private_key, *, sub: str, email: str, name: str = "Test User") -> str:
    now = int(time.time())
    return jwt.encode(
        {
            "iss": "https://accounts.google.com",
            "sub": sub,
            "aud": TEST_AUDIENCE,
            "email": email,
            "email_verified": True,
            "name": name,
            "picture": "https://example/pic.jpg",
            "iat": now,
            "exp": now + 3600,
        },
        private_key,
        algorithm="RS256",
    )


@pytest.mark.integration
class TestGoogleAuth:
    async def test_first_signin_creates_user_and_returns_token(self, google_client):
        client, private_key = google_client
        id_token = _mint_id_token(private_key, sub="google-sub-001", email="alice@example.com")

        r = await client.post("/v1/auth/google", json={"id_token": id_token})
        assert r.status_code == 200, r.text

        data = r.json()
        assert data["token"].startswith("ch_")
        assert len(data["token"]) == 67
        assert set(data["scopes"]) == {"push", "pull", "search", "read"}
        assert data["user"]["email"] == "alice@example.com"
        assert data["user"]["display_name"] == "Test User"
        assert data["workspace_id"]

    async def test_returned_token_authenticates_me_endpoint(self, google_client):
        client, private_key = google_client
        id_token = _mint_id_token(private_key, sub="google-sub-002", email="bob@example.com")

        r = await client.post("/v1/auth/google", json={"id_token": id_token})
        assert r.status_code == 200
        token = r.json()["token"]

        me = await client.get("/v1/me", headers={"Authorization": f"Bearer {token}"})
        assert me.status_code == 200
        assert me.json()["user_id"] == r.json()["user"]["user_id"]

    async def test_repeated_signin_same_google_account_returns_same_user_id(self, google_client):
        client, private_key = google_client
        sub = "google-sub-003"
        a = await client.post(
            "/v1/auth/google",
            json={"id_token": _mint_id_token(private_key, sub=sub, email="carol@example.com")},
        )
        b = await client.post(
            "/v1/auth/google",
            json={"id_token": _mint_id_token(private_key, sub=sub, email="carol@example.com")},
        )
        assert a.status_code == 200 and b.status_code == 200
        assert a.json()["user"]["user_id"] == b.json()["user"]["user_id"]
        assert a.json()["workspace_id"] == b.json()["workspace_id"]
        # New token minted each time though.
        assert a.json()["token"] != b.json()["token"]

    async def test_invalid_id_token_returns_401(self, google_client):
        client, _ = google_client
        r = await client.post("/v1/auth/google", json={"id_token": "not-a-real-jwt"})
        assert r.status_code == 401

    async def test_wrong_audience_returns_401(self, google_client):
        client, private_key = google_client
        now = int(time.time())
        bad_token = jwt.encode(
            {
                "iss": "https://accounts.google.com",
                "sub": "x",
                "aud": "other.apps.googleusercontent.com",
                "email": "x@example.com",
                "iat": now,
                "exp": now + 3600,
            },
            private_key,
            algorithm="RS256",
        )
        r = await client.post("/v1/auth/google", json={"id_token": bad_token})
        assert r.status_code == 401

    async def test_no_configured_client_ids_returns_401(self, google_client):
        client, private_key = google_client
        import contexthub_backend.config as cfg_module

        previous = cfg_module.settings.google_oauth_client_ids
        cfg_module.settings.google_oauth_client_ids = ""
        try:
            r = await client.post(
                "/v1/auth/google",
                json={
                    "id_token": _mint_id_token(
                        private_key, sub="anyone", email="x@example.com"
                    )
                },
            )
            assert r.status_code == 401
        finally:
            cfg_module.settings.google_oauth_client_ids = previous
