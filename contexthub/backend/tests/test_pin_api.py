"""Integration tests for pin/unpin endpoints + pinned-list endpoint.

Covers:
  - POST   /v1/pushes/{id}/pin           — pins, returns row with pinned_at set
  - POST   /v1/pushes/{id}/pin (twice)   — idempotent, pinned_at unchanged
  - DELETE /v1/pushes/{id}/pin           — unpins
  - DELETE /v1/pushes/{id}/pin (twice)   — idempotent
  - 404 on unknown push id
  - RLS: user A cannot pin user B's push (gets 404, not 403, because the
         row is invisible to the wrong user — this is the desired leak-free behavior)
  - GET    /v1/workspaces/{id}/pushes/pinned — returns only caller's pins,
                                              newest pin first, excludes soft-deleted
"""

from __future__ import annotations

import os
import uuid

import psycopg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from contexthub_backend.auth import dependencies as auth_deps
from contexthub_backend.auth.jwt import make_test_jwt
from contexthub_backend.db.base import make_async_engine
from contexthub_backend.db.short_id import uuid7
from tests.conftest import _psycopg_url

TEST_JWT_SECRET = "test-secret-not-for-production-at-least-32-bytes"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="module")
async def async_engine(db_engine):
    from contexthub_backend.config import settings

    async_url = settings.database_url.replace("+psycopg://", "+asyncpg://")
    if "+asyncpg://" not in async_url:
        async_url = async_url.replace("postgresql://", "postgresql+asyncpg://", 1)

    engine = make_async_engine(async_url)
    auth_deps._set_engine(engine)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="module")
def pin_users(db_engine):
    """Two users, each with a workspace and a push. user_a also has a soft-deleted push."""
    user_a = uuid7()
    user_b = uuid7()
    ws_a = uuid7()
    ws_b = uuid7()
    push_a = uuid7()
    push_b = uuid7()
    push_a_deleted = uuid7()
    push_a_second = uuid7()

    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        for uid, email in [
            (user_a, "pin-alice@test.local"),
            (user_b, "pin-bob@test.local"),
        ]:
            conn.execute(
                "INSERT INTO auth.users (id, email) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (str(uid), email),
            )
            conn.execute(
                "INSERT INTO profiles (user_id, display_name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (str(uid), f"Pin User {uid}"),
            )
        conn.execute(
            "INSERT INTO interchange_format_versions (version, json_schema) "
            "VALUES ('ch.v0.1', '{}'::jsonb) ON CONFLICT DO NOTHING"
        )
        for wid, uid, slug in [(ws_a, user_a, "pin-a"), (ws_b, user_b, "pin-b")]:
            conn.execute(
                "INSERT INTO workspaces (id, user_id, name, slug) "
                "VALUES (%s, %s, %s, %s)",
                (str(wid), str(uid), f"WS {slug}", slug),
            )
        push_rows = [
            (push_a, ws_a, user_a, None),
            (push_a_second, ws_a, user_a, None),
            (push_b, ws_b, user_b, None),
            (push_a_deleted, ws_a, user_a, "now()"),
        ]
        for pid, wid, uid, deleted in push_rows:
            if deleted:
                conn.execute(
                    "INSERT INTO pushes (id, workspace_id, user_id, source_platform, deleted_at) "
                    "VALUES (%s, %s, %s, 'claude_ai', now())",
                    (str(pid), str(wid), str(uid)),
                )
            else:
                conn.execute(
                    "INSERT INTO pushes (id, workspace_id, user_id, source_platform) "
                    "VALUES (%s, %s, %s, 'claude_ai')",
                    (str(pid), str(wid), str(uid)),
                )
    return {
        "user_a": user_a,
        "user_b": user_b,
        "ws_a": ws_a,
        "ws_b": ws_b,
        "push_a": push_a,
        "push_a_second": push_a_second,
        "push_b": push_b,
        "push_a_deleted": push_a_deleted,
    }


@pytest_asyncio.fixture(scope="module")
async def client(async_engine):
    os.environ.setdefault("SUPABASE_JWT_SECRET", TEST_JWT_SECRET)

    from contexthub_backend.api.app import create_app
    from contexthub_backend.config import Settings
    import contexthub_backend.config as cfg_module

    cfg_module.settings = Settings(
        supabase_jwt_secret=TEST_JWT_SECRET,
        database_url=cfg_module.settings.database_url,
    )

    app = create_app(engine=async_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _bearer(uid: uuid.UUID) -> dict[str, str]:
    return {"Authorization": f"Bearer {make_test_jwt(uid, TEST_JWT_SECRET)}"}


# ---------------------------------------------------------------------------
# POST /v1/pushes/{id}/pin
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestPinPush:
    async def test_pin_sets_pinned_at(self, client, pin_users):
        r = await client.post(
            f"/v1/pushes/{pin_users['push_a']}/pin",
            headers=_bearer(pin_users["user_a"]),
        )
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["id"] == str(pin_users["push_a"])
        assert body["pinned_at"] is not None

    async def test_pin_is_idempotent(self, client, pin_users):
        # Already pinned by previous test; re-pin should not advance pinned_at.
        first = await client.post(
            f"/v1/pushes/{pin_users['push_a']}/pin",
            headers=_bearer(pin_users["user_a"]),
        )
        second = await client.post(
            f"/v1/pushes/{pin_users['push_a']}/pin",
            headers=_bearer(pin_users["user_a"]),
        )
        assert first.status_code == second.status_code == 200
        assert first.json()["pinned_at"] == second.json()["pinned_at"]

    async def test_pin_unknown_push_returns_404(self, client, pin_users):
        r = await client.post(
            f"/v1/pushes/{uuid7()}/pin",
            headers=_bearer(pin_users["user_a"]),
        )
        assert r.status_code == 404

    async def test_pin_other_users_push_returns_404(self, client, pin_users):
        # user_a tries to pin user_b's push — RLS hides it, so 404 (not 403).
        r = await client.post(
            f"/v1/pushes/{pin_users['push_b']}/pin",
            headers=_bearer(pin_users["user_a"]),
        )
        assert r.status_code == 404

    async def test_pin_soft_deleted_returns_404(self, client, pin_users):
        r = await client.post(
            f"/v1/pushes/{pin_users['push_a_deleted']}/pin",
            headers=_bearer(pin_users["user_a"]),
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# DELETE /v1/pushes/{id}/pin
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestUnpinPush:
    async def test_unpin_clears_pinned_at(self, client, pin_users):
        # Ensure pinned first.
        await client.post(
            f"/v1/pushes/{pin_users['push_a_second']}/pin",
            headers=_bearer(pin_users["user_a"]),
        )
        r = await client.delete(
            f"/v1/pushes/{pin_users['push_a_second']}/pin",
            headers=_bearer(pin_users["user_a"]),
        )
        assert r.status_code == 200
        assert r.json()["pinned_at"] is None

    async def test_unpin_is_idempotent(self, client, pin_users):
        # Already unpinned; calling again should still return 200 with pinned_at null.
        r = await client.delete(
            f"/v1/pushes/{pin_users['push_a_second']}/pin",
            headers=_bearer(pin_users["user_a"]),
        )
        assert r.status_code == 200
        assert r.json()["pinned_at"] is None

    async def test_unpin_other_users_push_returns_404(self, client, pin_users):
        r = await client.delete(
            f"/v1/pushes/{pin_users['push_b']}/pin",
            headers=_bearer(pin_users["user_a"]),
        )
        assert r.status_code == 404


# ---------------------------------------------------------------------------
# GET /v1/workspaces/{id}/pushes/pinned
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestListPinned:
    async def test_returns_only_pinned_pushes(self, client, pin_users):
        # Pin push_a and push_a_second; check listing.
        await client.post(
            f"/v1/pushes/{pin_users['push_a']}/pin",
            headers=_bearer(pin_users["user_a"]),
        )
        await client.post(
            f"/v1/pushes/{pin_users['push_a_second']}/pin",
            headers=_bearer(pin_users["user_a"]),
        )

        r = await client.get(
            f"/v1/workspaces/{pin_users['ws_a']}/pushes/pinned",
            headers=_bearer(pin_users["user_a"]),
        )
        assert r.status_code == 200
        rows = r.json()
        ids = {row["id"] for row in rows}
        assert str(pin_users["push_a"]) in ids
        assert str(pin_users["push_a_second"]) in ids
        # Soft-deleted push must not appear even if it had been pinned.
        assert str(pin_users["push_a_deleted"]) not in ids

    async def test_returns_newest_pin_first(self, client, pin_users):
        r = await client.get(
            f"/v1/workspaces/{pin_users['ws_a']}/pushes/pinned",
            headers=_bearer(pin_users["user_a"]),
        )
        rows = r.json()
        assert len(rows) >= 2
        pinned_ats = [row["pinned_at"] for row in rows]
        assert pinned_ats == sorted(pinned_ats, reverse=True)

    async def test_rls_hides_other_users_pins(self, client, pin_users):
        # user_b pins their own push.
        await client.post(
            f"/v1/pushes/{pin_users['push_b']}/pin",
            headers=_bearer(pin_users["user_b"]),
        )
        # user_a asks for ws_b's pinned list — RLS makes it empty.
        r = await client.get(
            f"/v1/workspaces/{pin_users['ws_b']}/pushes/pinned",
            headers=_bearer(pin_users["user_a"]),
        )
        assert r.status_code == 200
        assert r.json() == []
