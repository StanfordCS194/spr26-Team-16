"""Integration tests for /v1/admin/* routes.

Auth strategy
-------------
Admin routes go through ``require_admin_scope`` which depends on
``get_current_user``. To avoid the SHA-256 token-hash insertion dance — and
because ``ALL_SCOPES`` in auth/tokens.py does not include "admin", so
``mint_token`` rejects it — we use FastAPI's ``app.dependency_overrides``
to swap ``get_current_user`` for a fixture-controlled stub that returns an
AuthUser with whatever scopes the test wants. This keeps each test focused
on the route's behavior rather than token plumbing.

For unauthenticated tests we omit the override so the real dependency runs;
sending a bogus Bearer token yields 401 from ``verify_api_token``.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

import psycopg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from contexthub_backend.auth import dependencies as auth_deps
from contexthub_backend.auth.dependencies import AuthUser, get_current_user
from contexthub_backend.db.base import make_async_engine
from tests.conftest import _psycopg_url

TEST_JWT_SECRET = "test-secret-not-for-production-at-least-32-bytes"


# ---------------------------------------------------------------------------
# Engine + app fixtures
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


@pytest_asyncio.fixture(scope="function")
async def app_and_client(async_engine):
    """Function-scoped app so ``dependency_overrides`` resets between tests."""
    import contexthub_backend.config as cfg_module
    from contexthub_backend.api.app import create_app

    cfg_module.settings.supabase_jwt_secret = TEST_JWT_SECRET

    app = create_app(engine=async_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield app, c


# ---------------------------------------------------------------------------
# Test users / workspaces
# ---------------------------------------------------------------------------


@pytest.fixture(scope="module")
def admin_users(db_engine):
    """Two users + one workspace for admin-route tests."""
    user_admin = uuid.uuid4()
    user_plain = uuid.uuid4()
    workspace_id = uuid.uuid4()

    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO interchange_format_versions (version, json_schema) "
            "VALUES ('ch.v0.1', '{}'::jsonb) ON CONFLICT DO NOTHING"
        )
        for uid, email in [
            (user_admin, "admin-routes-admin@test.local"),
            (user_plain, "admin-routes-plain@test.local"),
        ]:
            conn.execute(
                "INSERT INTO auth.users (id, email) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (str(uid), email),
            )
            conn.execute(
                "INSERT INTO profiles (user_id, display_name) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (str(uid), f"User {uid}"),
            )
        conn.execute(
            "INSERT INTO workspaces (id, user_id, name, slug) VALUES (%s, %s, %s, %s) ON CONFLICT DO NOTHING",
            (str(workspace_id), str(user_admin), "Admin WS", f"admin-ws-{str(workspace_id)[:8]}"),
        )
    return {
        "admin_user_id": user_admin,
        "plain_user_id": user_plain,
        "workspace_id": workspace_id,
    }


# ---------------------------------------------------------------------------
# Auth override helpers
# ---------------------------------------------------------------------------


def _override_user(app, *, user_id: uuid.UUID, scopes: list[str], auth_type: str = "api_token") -> None:
    async def _fake_get_current_user() -> AuthUser:
        return AuthUser(user_id=user_id, scopes=list(scopes), auth_type=auth_type)

    app.dependency_overrides[get_current_user] = _fake_get_current_user


def _override_admin(app, user_id: uuid.UUID) -> None:
    _override_user(app, user_id=user_id, scopes=["push", "read", "admin"])


def _override_non_admin(app, user_id: uuid.UUID) -> None:
    _override_user(app, user_id=user_id, scopes=["push", "read", "search", "pull"])


# A clearly-bogus ch_-prefixed token: format ok (lookup runs) but no DB row → 401.
BOGUS_API_TOKEN = "ch_" + ("0" * 64)


# ---------------------------------------------------------------------------
# Helpers for seeding pushes
# ---------------------------------------------------------------------------


async def _seed_soft_deleted_pushes(async_engine, workspace_id, user_id, count: int) -> list[uuid.UUID]:
    """Insert ``count`` pushes whose deleted_at is well past the soft-delete cutoff."""
    from contexthub_backend.config import settings as _settings

    days_ago = _settings.retention_soft_delete_days + 30
    deleted_at = datetime.now(timezone.utc) - timedelta(days=days_ago)
    push_ids: list[uuid.UUID] = []
    async with async_engine.begin() as conn:
        for _ in range(count):
            pid = uuid.uuid4()
            push_ids.append(pid)
            await conn.execute(
                text(
                    "INSERT INTO pushes (id, workspace_id, user_id, source_platform, "
                    "interchange_version, status, created_at, updated_at, deleted_at) "
                    "VALUES (:id, :ws, :u, 'claude_ai', 'ch.v0.1', 'ready', "
                    ":created_at, :updated_at, :deleted_at)"
                ),
                {
                    "id": str(pid),
                    "ws": str(workspace_id),
                    "u": str(user_id),
                    "created_at": deleted_at,
                    "updated_at": deleted_at,
                    "deleted_at": deleted_at,
                },
            )
    return push_ids


async def _seed_stuck_pushes(async_engine, workspace_id, user_id, count: int) -> list[uuid.UUID]:
    """Insert ``count`` pending pushes with updated_at older than stuck threshold."""
    from contexthub_backend.config import settings as _settings

    minutes_ago = _settings.stuck_push_minutes + 30
    updated_at = datetime.now(timezone.utc) - timedelta(minutes=minutes_ago)
    push_ids: list[uuid.UUID] = []
    async with async_engine.begin() as conn:
        for _ in range(count):
            pid = uuid.uuid4()
            push_ids.append(pid)
            await conn.execute(
                text(
                    "INSERT INTO pushes (id, workspace_id, user_id, source_platform, "
                    "interchange_version, status, created_at, updated_at) "
                    "VALUES (:id, :ws, :u, 'claude_ai', 'ch.v0.1', 'pending', "
                    ":created_at, :updated_at)"
                ),
                {
                    "id": str(pid),
                    "ws": str(workspace_id),
                    "u": str(user_id),
                    "created_at": updated_at,
                    "updated_at": updated_at,
                },
            )
    return push_ids


async def _delete_pushes(async_engine, push_ids: list[uuid.UUID]) -> None:
    if not push_ids:
        return
    async with async_engine.begin() as conn:
        await conn.execute(
            text("DELETE FROM pushes WHERE id = ANY(cast(:ids as uuid[]))"),
            {"ids": [str(p) for p in push_ids]},
        )


async def _count_pushes(async_engine) -> int:
    async with async_engine.begin() as conn:
        r = await conn.execute(text("SELECT count(*) FROM pushes"))
        return r.scalar_one()


# ---------------------------------------------------------------------------
# Recording fake for enqueue_job
# ---------------------------------------------------------------------------


class _EnqueueRecorder:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []

    async def __call__(self, job_name: str, **kwargs: Any) -> None:
        self.calls.append((job_name, dict(kwargs)))


# ---------------------------------------------------------------------------
# GET /v1/admin/retention/dry-run
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRetentionDryRun:
    async def test_dry_run_unauth_returns_401(self, app_and_client):
        _, client = app_and_client
        r = await client.get(
            "/v1/admin/retention/dry-run",
            headers={"Authorization": f"Bearer {BOGUS_API_TOKEN}"},
        )
        assert r.status_code == 401

    async def test_dry_run_requires_admin_scope(self, app_and_client, admin_users):
        app, client = app_and_client
        _override_non_admin(app, admin_users["plain_user_id"])
        r = await client.get("/v1/admin/retention/dry-run")
        assert r.status_code == 403

    async def test_dry_run_returns_all_5_keys(self, app_and_client, admin_users):
        app, client = app_and_client
        _override_admin(app, admin_users["admin_user_id"])
        r = await client.get("/v1/admin/retention/dry-run")
        assert r.status_code == 200
        body = r.json()
        for key in (
            "purge_soft_deleted_pushes",
            "purge_failed_pushes",
            "purge_audit_log",
            "purge_revoked_tokens",
            "stuck_pushes",
        ):
            assert key in body, f"missing key {key} in dry-run response"

    async def test_dry_run_modifies_no_data(self, app_and_client, admin_users, async_engine):
        app, client = app_and_client
        _override_admin(app, admin_users["admin_user_id"])

        before = await _count_pushes(async_engine)
        r = await client.get("/v1/admin/retention/dry-run")
        assert r.status_code == 200
        after = await _count_pushes(async_engine)
        assert before == after

    async def test_dry_run_counts_match_real_state(self, app_and_client, admin_users, async_engine):
        app, client = app_and_client
        _override_admin(app, admin_users["admin_user_id"])

        seeded = await _seed_soft_deleted_pushes(
            async_engine,
            admin_users["workspace_id"],
            admin_users["admin_user_id"],
            3,
        )
        try:
            r = await client.get("/v1/admin/retention/dry-run")
            assert r.status_code == 200
            body = r.json()
            assert body["purge_soft_deleted_pushes"]["would_delete"] >= 3
        finally:
            await _delete_pushes(async_engine, seeded)


# ---------------------------------------------------------------------------
# GET /v1/admin/pushes/stuck
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestStuckPushes:
    async def test_stuck_unauth_401(self, app_and_client):
        _, client = app_and_client
        r = await client.get(
            "/v1/admin/pushes/stuck",
            headers={"Authorization": f"Bearer {BOGUS_API_TOKEN}"},
        )
        assert r.status_code == 401

    async def test_stuck_non_admin_403(self, app_and_client, admin_users):
        app, client = app_and_client
        _override_non_admin(app, admin_users["plain_user_id"])
        r = await client.get("/v1/admin/pushes/stuck")
        assert r.status_code == 403

    async def test_stuck_empty_list_returns_zero_count(
        self, app_and_client, admin_users, async_engine
    ):
        app, client = app_and_client
        _override_admin(app, admin_users["admin_user_id"])

        # Ensure no stuck pushes exist by removing any pending/processing rows.
        async with async_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM pushes WHERE status IN ('pending', 'processing')")
            )

        r = await client.get("/v1/admin/pushes/stuck")
        assert r.status_code == 200
        body = r.json()
        assert body["count"] == 0
        assert body["items"] == []

    async def test_stuck_returns_correctly_serialized_items(
        self, app_and_client, admin_users, async_engine
    ):
        app, client = app_and_client
        _override_admin(app, admin_users["admin_user_id"])

        # Clear pre-existing stuck pushes for a deterministic count assertion.
        async with async_engine.begin() as conn:
            await conn.execute(
                text("DELETE FROM pushes WHERE status IN ('pending', 'processing')")
            )

        seeded = await _seed_stuck_pushes(
            async_engine,
            admin_users["workspace_id"],
            admin_users["admin_user_id"],
            2,
        )
        try:
            r = await client.get("/v1/admin/pushes/stuck")
            assert r.status_code == 200
            body = r.json()
            assert body["count"] == 2
            assert len(body["items"]) == 2

            seeded_ids = {str(p) for p in seeded}
            for item in body["items"]:
                # All UUIDs are stringified.
                assert isinstance(item["push_id"], str)
                uuid.UUID(item["push_id"])
                assert isinstance(item["user_id"], str)
                uuid.UUID(item["user_id"])
                assert isinstance(item["workspace_id"], str)
                uuid.UUID(item["workspace_id"])
                assert item["status"] in ("pending", "processing")
                assert isinstance(item["minutes_stuck"], int)
                # failure_reason key is present even when null.
                assert "failure_reason" in item

            assert {item["push_id"] for item in body["items"]} == seeded_ids
        finally:
            await _delete_pushes(async_engine, seeded)

    async def test_stuck_threshold_minutes_field_present(
        self, app_and_client, admin_users
    ):
        app, client = app_and_client
        _override_admin(app, admin_users["admin_user_id"])

        r = await client.get("/v1/admin/pushes/stuck")
        assert r.status_code == 200
        body = r.json()
        assert "threshold_minutes" in body
        assert isinstance(body["threshold_minutes"], int)
        assert body["threshold_minutes"] > 0


# ---------------------------------------------------------------------------
# POST /v1/admin/pushes/{push_id}/requeue
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestRequeuePush:
    async def test_requeue_unauth(self, app_and_client):
        _, client = app_and_client
        push_id = uuid.uuid4()
        r = await client.post(
            f"/v1/admin/pushes/{push_id}/requeue",
            headers={"Authorization": f"Bearer {BOGUS_API_TOKEN}"},
        )
        assert r.status_code == 401

    async def test_requeue_non_admin(self, app_and_client, admin_users):
        app, client = app_and_client
        _override_non_admin(app, admin_users["plain_user_id"])
        push_id = uuid.uuid4()
        r = await client.post(f"/v1/admin/pushes/{push_id}/requeue")
        assert r.status_code == 403

    async def test_requeue_returns_202_and_queued_payload(
        self, app_and_client, admin_users, monkeypatch
    ):
        app, client = app_and_client
        _override_admin(app, admin_users["admin_user_id"])

        recorder = _EnqueueRecorder()
        monkeypatch.setattr(
            "contexthub_backend.api.routes.admin.enqueue_job", recorder
        )

        push_id = uuid.uuid4()
        r = await client.post(f"/v1/admin/pushes/{push_id}/requeue")
        assert r.status_code == 202
        body = r.json()
        assert body["queued"] is True
        assert body["push_id"] == str(push_id)

        assert len(recorder.calls) == 1
        name, kwargs = recorder.calls[0]
        assert name == "requeue_push"
        assert kwargs["push_id"] == str(push_id)
        assert "request_id" in kwargs

    async def test_requeue_unknown_push_id_still_queues(
        self, app_and_client, admin_users, monkeypatch
    ):
        """Route does not validate push existence — worker handles missing rows."""
        app, client = app_and_client
        _override_admin(app, admin_users["admin_user_id"])

        recorder = _EnqueueRecorder()
        monkeypatch.setattr(
            "contexthub_backend.api.routes.admin.enqueue_job", recorder
        )

        # Random uuid that has no row in pushes.
        push_id = uuid.uuid4()
        r = await client.post(f"/v1/admin/pushes/{push_id}/requeue")
        assert r.status_code == 202
        assert r.json()["push_id"] == str(push_id)
        assert len(recorder.calls) == 1
        assert recorder.calls[0][0] == "requeue_push"
        assert recorder.calls[0][1]["push_id"] == str(push_id)

    async def test_requeue_invalid_uuid_returns_422(
        self, app_and_client, admin_users, monkeypatch
    ):
        app, client = app_and_client
        _override_admin(app, admin_users["admin_user_id"])

        recorder = _EnqueueRecorder()
        monkeypatch.setattr(
            "contexthub_backend.api.routes.admin.enqueue_job", recorder
        )

        r = await client.post("/v1/admin/pushes/not-a-uuid/requeue")
        assert r.status_code == 422
        # Bad-request: enqueue must NOT have been called.
        assert recorder.calls == []


# ---------------------------------------------------------------------------
# POST /v1/admin/users/{user_id}/delete
# ---------------------------------------------------------------------------


@pytest.mark.integration
class TestCascadeDeleteUser:
    async def test_delete_unauth(self, app_and_client):
        _, client = app_and_client
        target = uuid.uuid4()
        r = await client.post(
            f"/v1/admin/users/{target}/delete",
            headers={"Authorization": f"Bearer {BOGUS_API_TOKEN}"},
            json={"confirm": "DELETE"},
        )
        assert r.status_code == 401

    async def test_delete_non_admin(self, app_and_client, admin_users):
        app, client = app_and_client
        _override_non_admin(app, admin_users["plain_user_id"])
        target = uuid.uuid4()
        r = await client.post(
            f"/v1/admin/users/{target}/delete",
            json={"confirm": "DELETE"},
        )
        assert r.status_code == 403

    async def test_delete_without_confirm_returns_422(
        self, app_and_client, admin_users
    ):
        app, client = app_and_client
        _override_admin(app, admin_users["admin_user_id"])
        target = uuid.uuid4()
        r = await client.post(
            f"/v1/admin/users/{target}/delete",
            json={},
        )
        assert r.status_code == 422

    async def test_delete_with_wrong_confirm_lowercase_returns_422(
        self, app_and_client, admin_users, monkeypatch
    ):
        app, client = app_and_client
        _override_admin(app, admin_users["admin_user_id"])

        recorder = _EnqueueRecorder()
        monkeypatch.setattr(
            "contexthub_backend.api.routes.admin.enqueue_job", recorder
        )

        target = uuid.uuid4()
        r = await client.post(
            f"/v1/admin/users/{target}/delete",
            json={"confirm": "delete"},
        )
        assert r.status_code == 422
        assert recorder.calls == []

    async def test_delete_with_wrong_confirm_yes_returns_422(
        self, app_and_client, admin_users, monkeypatch
    ):
        app, client = app_and_client
        _override_admin(app, admin_users["admin_user_id"])

        recorder = _EnqueueRecorder()
        monkeypatch.setattr(
            "contexthub_backend.api.routes.admin.enqueue_job", recorder
        )

        target = uuid.uuid4()
        r = await client.post(
            f"/v1/admin/users/{target}/delete",
            json={"confirm": "yes"},
        )
        assert r.status_code == 422
        assert recorder.calls == []

    async def test_delete_with_confirm_DELETE_returns_202_and_enqueues(
        self, app_and_client, admin_users, monkeypatch
    ):
        app, client = app_and_client
        _override_admin(app, admin_users["admin_user_id"])

        recorder = _EnqueueRecorder()
        monkeypatch.setattr(
            "contexthub_backend.api.routes.admin.enqueue_job", recorder
        )

        target = uuid.uuid4()
        r = await client.post(
            f"/v1/admin/users/{target}/delete",
            json={"confirm": "DELETE"},
        )
        assert r.status_code == 202
        body = r.json()
        assert body["queued"] is True
        assert body["user_id"] == str(target)

        assert len(recorder.calls) == 1
        name, kwargs = recorder.calls[0]
        assert name == "cascade_delete_user"
        assert kwargs["user_id"] == str(target)
        assert "request_id" in kwargs

    async def test_delete_invalid_user_uuid_returns_422(
        self, app_and_client, admin_users, monkeypatch
    ):
        app, client = app_and_client
        _override_admin(app, admin_users["admin_user_id"])

        recorder = _EnqueueRecorder()
        monkeypatch.setattr(
            "contexthub_backend.api.routes.admin.enqueue_job", recorder
        )

        r = await client.post(
            "/v1/admin/users/not-a-uuid/delete",
            json={"confirm": "DELETE"},
        )
        assert r.status_code == 422
        assert recorder.calls == []
