from __future__ import annotations

import uuid

import psycopg
import pytest
import pytest_asyncio
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.config import settings
from contexthub_backend.db.base import make_async_engine
from contexthub_backend.db.models import AuditLog, Push
from contexthub_backend.jobs.tasks import requeue_push
from tests.conftest import _psycopg_url


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeArqRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def enqueue_job(self, name: str, **kwargs) -> None:
        self.calls.append((name, kwargs))


def _ctx_with_redis() -> tuple[dict, FakeArqRedis]:
    fake = FakeArqRedis()
    return {"redis": fake}, fake


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="function")
async def async_engine(db_engine):
    engine = make_async_engine(settings.async_database_url)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture(scope="function")
async def async_session(async_engine):
    async with AsyncSession(async_engine) as session:
        yield session


# ---------------------------------------------------------------------------
# Seed helpers
# ---------------------------------------------------------------------------


def _seed_user_and_workspace(prefix: str = "rqp") -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO interchange_format_versions (version, json_schema) "
            "VALUES ('ch.v0.1', '{}'::jsonb) ON CONFLICT DO NOTHING"
        )
        conn.execute(
            "INSERT INTO auth.users (id, email) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (str(user_id), f"{prefix}-{str(user_id).replace('-', '')[:10]}@rqp.local"),
        )
        conn.execute(
            "INSERT INTO workspaces (id, user_id, name, slug) VALUES (%s, %s, %s, %s)",
            (str(ws_id), str(user_id), f"{prefix}-ws", f"{prefix}-{str(ws_id)[:8]}"),
        )
    return user_id, ws_id


def _insert_push(
    *,
    workspace_id: uuid.UUID,
    user_id: uuid.UUID,
    status: str,
    failure_reason: str | None = None,
) -> uuid.UUID:
    push_id = uuid.uuid4()
    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        conn.execute(
            """
            INSERT INTO pushes (id, workspace_id, user_id, source_platform,
                                interchange_version, status, failure_reason)
            VALUES (%s, %s, %s, 'claude_ai', 'ch.v0.1', %s, %s)
            """,
            (str(push_id), str(workspace_id), str(user_id), status, failure_reason),
        )
    return push_id


async def _audit_for_push(session: AsyncSession, push_id: uuid.UUID) -> list[AuditLog]:
    rows = await session.execute(
        select(AuditLog)
        .where(
            AuditLog.action == "push.requeued",
            AuditLog.resource_id == str(push_id),
        )
        .order_by(AuditLog.created_at)
    )
    return list(rows.scalars().all())


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_requeue_push_pending_pushes_back_to_pending_and_enqueues(
    async_engine, async_session
):
    user_id, ws_id = _seed_user_and_workspace("rqp-pen")
    push_id = _insert_push(workspace_id=ws_id, user_id=user_id, status="pending")
    ctx, fake = _ctx_with_redis()
    request_id = "req-" + uuid.uuid4().hex[:8]

    result = await requeue_push(ctx, push_id=str(push_id), request_id=request_id)

    assert result == "pending"
    push = await async_session.get(Push, push_id)
    assert push.status == "pending"
    assert push.failure_reason is None

    assert len(fake.calls) == 1
    name, kwargs = fake.calls[0]
    assert name == "summarize_push"
    assert kwargs["push_id"] == str(push_id)
    assert kwargs["request_id"] == request_id
    assert kwargs["scrub_flags"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_requeue_push_failed_resets_failure_reason(async_engine, async_session):
    user_id, ws_id = _seed_user_and_workspace("rqp-fai")
    push_id = _insert_push(
        workspace_id=ws_id,
        user_id=user_id,
        status="failed",
        failure_reason="boom",
    )
    ctx, fake = _ctx_with_redis()
    request_id = "req-" + uuid.uuid4().hex[:8]

    result = await requeue_push(ctx, push_id=str(push_id), request_id=request_id)

    assert result == "pending"
    push = await async_session.get(Push, push_id)
    assert push.status == "pending"
    assert push.failure_reason is None
    assert len(fake.calls) == 1


@pytest.mark.integration
@pytest.mark.asyncio
async def test_requeue_push_processing_resets_to_pending(async_engine, async_session):
    user_id, ws_id = _seed_user_and_workspace("rqp-pro")
    push_id = _insert_push(workspace_id=ws_id, user_id=user_id, status="processing")
    ctx, fake = _ctx_with_redis()
    request_id = "req-" + uuid.uuid4().hex[:8]

    result = await requeue_push(ctx, push_id=str(push_id), request_id=request_id)

    assert result == "pending"
    push = await async_session.get(Push, push_id)
    assert push.status == "pending"
    assert push.failure_reason is None
    assert len(fake.calls) == 1
    assert fake.calls[0][0] == "summarize_push"


@pytest.mark.integration
@pytest.mark.asyncio
async def test_requeue_push_skipped_for_ready_status(async_engine, async_session):
    user_id, ws_id = _seed_user_and_workspace("rqp-rdy")
    push_id = _insert_push(workspace_id=ws_id, user_id=user_id, status="ready")
    ctx, fake = _ctx_with_redis()
    request_id = "req-" + uuid.uuid4().hex[:8]

    result = await requeue_push(ctx, push_id=str(push_id), request_id=request_id)

    assert result == "skipped:ready"
    push = await async_session.get(Push, push_id)
    assert push.status == "ready"
    assert fake.calls == []

    audit_rows = await _audit_for_push(async_session, push_id)
    assert audit_rows == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_requeue_push_missing_push_returns_missing_push(
    async_engine, async_session
):
    ctx, fake = _ctx_with_redis()
    request_id = "req-" + uuid.uuid4().hex[:8]
    nonexistent = uuid.uuid4()

    result = await requeue_push(ctx, push_id=str(nonexistent), request_id=request_id)
    assert result == "missing_push"
    assert fake.calls == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_requeue_push_writes_audit_with_previous_status(
    async_engine, async_session
):
    user_id, ws_id = _seed_user_and_workspace("rqp-aud")
    push_id = _insert_push(
        workspace_id=ws_id,
        user_id=user_id,
        status="failed",
        failure_reason="prior",
    )
    ctx, _ = _ctx_with_redis()
    request_id = "req-" + uuid.uuid4().hex[:8]

    result = await requeue_push(ctx, push_id=str(push_id), request_id=request_id)
    assert result == "pending"

    audit_rows = await _audit_for_push(async_session, push_id)
    assert len(audit_rows) == 1
    audit = audit_rows[0]
    assert audit.user_id == user_id
    assert audit.resource_type == "push"
    assert audit.resource_id == str(push_id)
    assert audit.request_id == request_id
    assert audit.metadata_json == {"previous_status": "failed"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_requeue_push_writes_audit_with_previous_status_processing(
    async_engine, async_session
):
    user_id, ws_id = _seed_user_and_workspace("rqp-aud2")
    push_id = _insert_push(workspace_id=ws_id, user_id=user_id, status="processing")
    ctx, _ = _ctx_with_redis()
    request_id = "req-" + uuid.uuid4().hex[:8]

    await requeue_push(ctx, push_id=str(push_id), request_id=request_id)
    audit_rows = await _audit_for_push(async_session, push_id)
    assert len(audit_rows) == 1
    assert audit_rows[0].metadata_json == {"previous_status": "processing"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_requeue_push_handles_none_redis(async_engine, async_session):
    user_id, ws_id = _seed_user_and_workspace("rqp-nor")
    push_id = _insert_push(
        workspace_id=ws_id,
        user_id=user_id,
        status="failed",
        failure_reason="boom",
    )
    request_id = "req-" + uuid.uuid4().hex[:8]

    result = await requeue_push({}, push_id=str(push_id), request_id=request_id)

    assert result == "pending"
    push = await async_session.get(Push, push_id)
    assert push.status == "pending"
    assert push.failure_reason is None

    audit_rows = await _audit_for_push(async_session, push_id)
    assert len(audit_rows) == 1
    assert audit_rows[0].metadata_json == {"previous_status": "failed"}


@pytest.mark.integration
@pytest.mark.asyncio
async def test_requeue_push_handles_explicit_none_redis_key(async_engine, async_session):
    user_id, ws_id = _seed_user_and_workspace("rqp-eno")
    push_id = _insert_push(workspace_id=ws_id, user_id=user_id, status="pending")
    request_id = "req-" + uuid.uuid4().hex[:8]

    result = await requeue_push(
        {"redis": None}, push_id=str(push_id), request_id=request_id
    )

    assert result == "pending"
    push = await async_session.get(Push, push_id)
    assert push.status == "pending"
