from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone

import psycopg
import pytest
import pytest_asyncio
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.config import settings
from contexthub_backend.db.base import make_async_engine
from contexthub_backend.db.models import (
    ApiToken,
    AuditLog,
    Profile,
    Pull,
    Push,
    Tag,
    Transcript,
    Workspace,
)
from contexthub_backend.jobs.tasks import (
    cascade_delete_user,
    detect_stuck_pushes,
    purge_audit_log,
    purge_failed_pushes,
    purge_revoked_tokens,
    purge_soft_deleted_pushes,
)
from tests.conftest import _psycopg_url


# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------


class FakeArqRedis:
    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def enqueue_job(self, name: str, **kwargs) -> None:
        self.calls.append((name, kwargs))


def _ctx(redis: FakeArqRedis | None = None) -> dict:
    return {"redis": redis if redis is not None else FakeArqRedis()}


# ---------------------------------------------------------------------------
# Async fixtures
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


def _seed_user_and_workspace(prefix: str = "ret") -> tuple[uuid.UUID, uuid.UUID]:
    user_id = uuid.uuid4()
    ws_id = uuid.uuid4()
    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO interchange_format_versions (version, json_schema) "
            "VALUES ('ch.v0.1', '{}'::jsonb) ON CONFLICT DO NOTHING"
        )
        conn.execute(
            "INSERT INTO auth.users (id, email) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (str(user_id), f"{prefix}-{str(user_id).replace('-', '')[:12]}@retjob.local"),
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
    status: str = "pending",
    soft_deleted_days_ago: int | None = None,
    failed_days_ago: int | None = None,
    updated_minutes_ago: int | None = None,
    failure_reason: str | None = None,
    with_transcript: bool = False,
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
        if soft_deleted_days_ago is not None:
            ts = datetime.now(timezone.utc) - timedelta(days=soft_deleted_days_ago)
            conn.execute(
                "UPDATE pushes SET deleted_at = %s WHERE id = %s",
                (ts, str(push_id)),
            )
        if failed_days_ago is not None:
            ts = datetime.now(timezone.utc) - timedelta(days=failed_days_ago)
            conn.execute(
                "UPDATE pushes SET created_at = %s WHERE id = %s",
                (ts, str(push_id)),
            )
        if updated_minutes_ago is not None:
            ts = datetime.now(timezone.utc) - timedelta(minutes=updated_minutes_ago)
            conn.execute(
                "UPDATE pushes SET updated_at = %s WHERE id = %s",
                (ts, str(push_id)),
            )
        if with_transcript:
            conn.execute(
                """
                INSERT INTO transcripts (push_id, storage_path, sha256,
                                         size_bytes, message_count)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    str(push_id),
                    f"workspace/{workspace_id}/{push_id}.json",
                    "0" * 64,
                    0,
                    0,
                ),
            )
    return push_id


def _backdate_audit_log(audit_id: uuid.UUID, days_ago: int) -> None:
    ts = datetime.now(timezone.utc) - timedelta(days=days_ago)
    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        conn.execute(
            "UPDATE audit_log SET created_at = %s WHERE id = %s",
            (ts, str(audit_id)),
        )


def _insert_audit_log(*, user_id: uuid.UUID | None = None, action: str = "test.event") -> uuid.UUID:
    log_id = uuid.uuid4()
    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO audit_log (id, user_id, action) VALUES (%s, %s, %s)",
            (str(log_id), str(user_id) if user_id else None, action),
        )
    return log_id


def _insert_api_token(
    *,
    user_id: uuid.UUID,
    revoked_days_ago: int | None = None,
) -> uuid.UUID:
    tok_id = uuid.uuid4()
    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO api_tokens (id, user_id, name, token_hash, scopes) "
            "VALUES (%s, %s, %s, %s, ARRAY['push'])",
            (str(tok_id), str(user_id), "test-token", "hash-" + str(tok_id)),
        )
        if revoked_days_ago is not None:
            ts = datetime.now(timezone.utc) - timedelta(days=revoked_days_ago)
            conn.execute(
                "UPDATE api_tokens SET revoked_at = %s WHERE id = %s",
                (ts, str(tok_id)),
            )
    return tok_id


async def _fetch_audit_rows(session: AsyncSession, action: str) -> list[AuditLog]:
    rows = await session.execute(
        select(AuditLog).where(AuditLog.action == action).order_by(AuditLog.created_at)
    )
    return list(rows.scalars().all())


async def _delete_audit_rows(session: AsyncSession, action: str) -> None:
    await session.execute(text("DELETE FROM audit_log WHERE action = :a"), {"a": action})
    await session.commit()


# ---------------------------------------------------------------------------
# purge_soft_deleted_pushes
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_purge_soft_deleted_pushes_wrapper_purges_old_rows_and_writes_audit(
    async_engine, async_session
):
    user_id, ws_id = _seed_user_and_workspace("psd1")
    old_push = _insert_push(
        workspace_id=ws_id,
        user_id=user_id,
        soft_deleted_days_ago=settings.retention_soft_delete_days + 5,
    )
    fresh_push = _insert_push(workspace_id=ws_id, user_id=user_id)

    result = await purge_soft_deleted_pushes(_ctx())

    assert result.startswith("purged:")
    n_purged = int(result.split(":")[1])
    assert n_purged >= 1

    surviving = await async_session.execute(
        select(Push.id).where(Push.id.in_([old_push, fresh_push]))
    )
    surviving_ids = {row[0] for row in surviving.all()}
    assert old_push not in surviving_ids
    assert fresh_push in surviving_ids

    audit_rows = await _fetch_audit_rows(async_session, "retention.purge_soft_deleted_pushes")
    assert len(audit_rows) >= 1
    latest = audit_rows[-1]
    assert latest.user_id is None
    assert latest.resource_type == "retention"
    assert latest.metadata_json is not None
    assert latest.metadata_json["job"] == "purge_soft_deleted_pushes"
    assert latest.metadata_json["rows_deleted"] >= 1

    await _delete_audit_rows(async_session, "retention.purge_soft_deleted_pushes")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_purge_soft_deleted_pushes_wrapper_zero_rows_still_writes_audit(
    async_engine, async_session
):
    await _delete_audit_rows(async_session, "retention.purge_soft_deleted_pushes")

    user_id, ws_id = _seed_user_and_workspace("psd0")
    _insert_push(workspace_id=ws_id, user_id=user_id)

    result = await purge_soft_deleted_pushes(_ctx())
    assert result == "purged:0"

    audit_rows = await _fetch_audit_rows(async_session, "retention.purge_soft_deleted_pushes")
    assert len(audit_rows) == 1
    assert audit_rows[0].metadata_json["rows_deleted"] == 0
    assert audit_rows[0].metadata_json["job"] == "purge_soft_deleted_pushes"

    await _delete_audit_rows(async_session, "retention.purge_soft_deleted_pushes")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_purge_soft_deleted_pushes_wrapper_with_transcript_records_path(
    async_engine, async_session
):
    user_id, ws_id = _seed_user_and_workspace("psdt")
    _insert_push(
        workspace_id=ws_id,
        user_id=user_id,
        soft_deleted_days_ago=settings.retention_soft_delete_days + 1,
        with_transcript=True,
    )

    result = await purge_soft_deleted_pushes(_ctx())
    assert result.startswith("purged:")

    audit_rows = await _fetch_audit_rows(async_session, "retention.purge_soft_deleted_pushes")
    assert len(audit_rows) >= 1
    md = audit_rows[-1].metadata_json
    assert md["storage_paths_purged"] >= 1
    assert "rows_by_table" in md and md["rows_by_table"].get("pushes", 0) >= 1

    await _delete_audit_rows(async_session, "retention.purge_soft_deleted_pushes")


# ---------------------------------------------------------------------------
# purge_failed_pushes
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_purge_failed_pushes_wrapper_purges_old_rows_and_writes_audit(
    async_engine, async_session
):
    user_id, ws_id = _seed_user_and_workspace("pfp1")
    old_failed = _insert_push(
        workspace_id=ws_id,
        user_id=user_id,
        status="failed",
        failed_days_ago=settings.retention_failed_push_days + 3,
        failure_reason="timeout",
    )
    fresh_failed = _insert_push(
        workspace_id=ws_id,
        user_id=user_id,
        status="failed",
        failure_reason="timeout",
    )

    result = await purge_failed_pushes(_ctx())
    assert result.startswith("purged:")

    surviving = await async_session.execute(
        select(Push.id).where(Push.id.in_([old_failed, fresh_failed]))
    )
    ids = {row[0] for row in surviving.all()}
    assert old_failed not in ids
    assert fresh_failed in ids

    audit_rows = await _fetch_audit_rows(async_session, "retention.purge_failed_pushes")
    assert len(audit_rows) >= 1
    latest = audit_rows[-1]
    assert latest.user_id is None
    assert latest.resource_type == "retention"
    assert latest.metadata_json["job"] == "purge_failed_pushes"
    assert latest.metadata_json["rows_deleted"] >= 1

    await _delete_audit_rows(async_session, "retention.purge_failed_pushes")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_purge_failed_pushes_wrapper_zero_rows_still_writes_audit(
    async_engine, async_session
):
    await _delete_audit_rows(async_session, "retention.purge_failed_pushes")

    result = await purge_failed_pushes(_ctx())
    assert result.startswith("purged:")

    audit_rows = await _fetch_audit_rows(async_session, "retention.purge_failed_pushes")
    assert len(audit_rows) == 1
    assert audit_rows[0].metadata_json["job"] == "purge_failed_pushes"

    await _delete_audit_rows(async_session, "retention.purge_failed_pushes")


# ---------------------------------------------------------------------------
# purge_audit_log
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_purge_audit_log_wrapper_purges_old_rows_and_writes_audit(
    async_engine, async_session
):
    await _delete_audit_rows(async_session, "retention.purge_audit_log")
    await _delete_audit_rows(async_session, "test.ancient")
    await _delete_audit_rows(async_session, "test.recent")

    ancient_id = _insert_audit_log(action="test.ancient")
    _backdate_audit_log(ancient_id, settings.retention_audit_log_days + 5)
    recent_id = _insert_audit_log(action="test.recent")

    result = await purge_audit_log(_ctx())
    assert result.startswith("purged:")

    rows_remaining = await async_session.execute(
        select(AuditLog.id).where(AuditLog.id.in_([ancient_id, recent_id]))
    )
    remaining = {row[0] for row in rows_remaining.all()}
    assert ancient_id not in remaining
    assert recent_id in remaining

    audit_rows = await _fetch_audit_rows(async_session, "retention.purge_audit_log")
    assert len(audit_rows) >= 1
    latest = audit_rows[-1]
    assert latest.user_id is None
    assert latest.resource_type == "retention"
    assert latest.metadata_json["job"] == "purge_audit_log"
    assert latest.metadata_json["rows_deleted"] >= 1

    await _delete_audit_rows(async_session, "retention.purge_audit_log")
    await _delete_audit_rows(async_session, "test.recent")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_purge_audit_log_wrapper_zero_rows_still_writes_audit(
    async_engine, async_session
):
    await _delete_audit_rows(async_session, "retention.purge_audit_log")

    result = await purge_audit_log(_ctx())
    assert result.startswith("purged:")

    audit_rows = await _fetch_audit_rows(async_session, "retention.purge_audit_log")
    assert len(audit_rows) == 1
    assert audit_rows[0].metadata_json["job"] == "purge_audit_log"

    await _delete_audit_rows(async_session, "retention.purge_audit_log")


# ---------------------------------------------------------------------------
# purge_revoked_tokens
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_purge_revoked_tokens_wrapper_purges_old_rows_and_writes_audit(
    async_engine, async_session
):
    user_id, _ = _seed_user_and_workspace("prt1")
    old_tok = _insert_api_token(
        user_id=user_id,
        revoked_days_ago=settings.retention_revoked_token_days + 5,
    )
    fresh_tok = _insert_api_token(user_id=user_id)
    fresh_revoked = _insert_api_token(user_id=user_id, revoked_days_ago=1)

    result = await purge_revoked_tokens(_ctx())
    assert result.startswith("purged:")

    rows = await async_session.execute(
        select(ApiToken.id).where(ApiToken.id.in_([old_tok, fresh_tok, fresh_revoked]))
    )
    surviving = {row[0] for row in rows.all()}
    assert old_tok not in surviving
    assert fresh_tok in surviving
    assert fresh_revoked in surviving

    audit_rows = await _fetch_audit_rows(async_session, "retention.purge_revoked_tokens")
    assert len(audit_rows) >= 1
    latest = audit_rows[-1]
    assert latest.user_id is None
    assert latest.resource_type == "retention"
    assert latest.metadata_json["job"] == "purge_revoked_tokens"
    assert latest.metadata_json["rows_deleted"] >= 1

    await _delete_audit_rows(async_session, "retention.purge_revoked_tokens")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_purge_revoked_tokens_wrapper_zero_rows_still_writes_audit(
    async_engine, async_session
):
    await _delete_audit_rows(async_session, "retention.purge_revoked_tokens")

    result = await purge_revoked_tokens(_ctx())
    assert result.startswith("purged:")

    audit_rows = await _fetch_audit_rows(async_session, "retention.purge_revoked_tokens")
    assert len(audit_rows) == 1
    assert audit_rows[0].metadata_json["job"] == "purge_revoked_tokens"

    await _delete_audit_rows(async_session, "retention.purge_revoked_tokens")


# ---------------------------------------------------------------------------
# cascade_delete_user
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cascade_delete_user_wrapper_full_cascade(async_engine, async_session):
    user_id, ws_id = _seed_user_and_workspace("cdu")
    push_id = _insert_push(
        workspace_id=ws_id, user_id=user_id, with_transcript=True
    )
    tok_id = _insert_api_token(user_id=user_id)

    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO tags (id, workspace_id, name, slug) VALUES (%s, %s, %s, %s)",
            (str(uuid.uuid4()), str(ws_id), "tag-a", f"tag-a-{str(ws_id)[:6]}"),
        )
        conn.execute(
            "INSERT INTO profiles (user_id, display_name) VALUES (%s, %s)",
            (str(user_id), "cdu user"),
        )
        conn.execute(
            "INSERT INTO pulls (id, user_id, target_platform, origin, resolution, "
            "push_ids, workspace_ids) VALUES (%s, %s, 'claude_ai', 'dashboard', "
            "'summary', ARRAY[%s]::text[], ARRAY[%s]::text[])",
            (str(uuid.uuid4()), str(user_id), str(push_id), str(ws_id)),
        )

    request_id = "req-cdu-" + uuid.uuid4().hex[:8]
    result = await cascade_delete_user(_ctx(), user_id=str(user_id), request_id=request_id)

    receipt = json.loads(result)
    assert receipt["job"] == "cascade_delete_user"
    assert receipt["rows_deleted"] >= 1
    assert "rows_by_table" in receipt
    assert receipt["rows_by_table"].get("pushes", 0) >= 1
    assert receipt["rows_by_table"].get("workspaces", 0) >= 1
    assert receipt["rows_by_table"].get("api_tokens", 0) >= 1
    assert receipt["rows_by_table"].get("profiles", 0) >= 1

    pushes_left = (
        await async_session.execute(select(Push.id).where(Push.user_id == user_id))
    ).all()
    assert pushes_left == []
    ws_left = (
        await async_session.execute(select(Workspace.id).where(Workspace.user_id == user_id))
    ).all()
    assert ws_left == []
    tags_left = (
        await async_session.execute(select(Tag.id).where(Tag.workspace_id == ws_id))
    ).all()
    assert tags_left == []
    tokens_left = (
        await async_session.execute(select(ApiToken.id).where(ApiToken.user_id == user_id))
    ).all()
    assert tokens_left == []
    pulls_left = (
        await async_session.execute(select(Pull.id).where(Pull.user_id == user_id))
    ).all()
    assert pulls_left == []
    profiles_left = (
        await async_session.execute(select(Profile.user_id).where(Profile.user_id == user_id))
    ).all()
    assert profiles_left == []
    transcripts_left = (
        await async_session.execute(
            select(Transcript.push_id).where(Transcript.push_id == push_id)
        )
    ).all()
    assert transcripts_left == []

    audit_rows = await _fetch_audit_rows(async_session, "user.deleted")
    relevant = [r for r in audit_rows if r.resource_id == str(user_id)]
    assert len(relevant) == 1
    audit = relevant[0]
    assert audit.user_id is None
    assert audit.resource_type == "user"
    assert audit.request_id == request_id
    assert audit.metadata_json["job"] == "cascade_delete_user"
    assert audit.metadata_json["rows_deleted"] >= 1

    _ = tok_id  # token presence implicitly validated above


@pytest.mark.integration
@pytest.mark.asyncio
async def test_cascade_delete_user_wrapper_no_data_writes_zero_receipt(
    async_engine, async_session
):
    user_id = uuid.uuid4()
    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO auth.users (id, email) VALUES (%s, %s) ON CONFLICT DO NOTHING",
            (str(user_id), f"empty-{str(user_id).replace('-', '')[:12]}@cdu.local"),
        )

    request_id = "req-cdu-empty-" + uuid.uuid4().hex[:6]
    result = await cascade_delete_user(_ctx(), user_id=str(user_id), request_id=request_id)
    receipt = json.loads(result)
    assert receipt["job"] == "cascade_delete_user"
    assert receipt["rows_deleted"] == 0

    audit_rows = await _fetch_audit_rows(async_session, "user.deleted")
    relevant = [r for r in audit_rows if r.resource_id == str(user_id)]
    assert len(relevant) == 1
    assert relevant[0].request_id == request_id


# ---------------------------------------------------------------------------
# detect_stuck_pushes
# ---------------------------------------------------------------------------


@pytest.mark.integration
@pytest.mark.asyncio
async def test_detect_stuck_pushes_wrapper_with_stuck_pushes_writes_audit(
    async_engine, async_session
):
    await _delete_audit_rows(async_session, "stuck_pushes.detected")

    user_id, ws_id = _seed_user_and_workspace("dsp1")
    stuck_minutes = settings.stuck_push_minutes + 30
    stuck_id = _insert_push(
        workspace_id=ws_id,
        user_id=user_id,
        status="processing",
        updated_minutes_ago=stuck_minutes,
    )
    fresh_id = _insert_push(workspace_id=ws_id, user_id=user_id, status="pending")

    result = await detect_stuck_pushes(_ctx())
    count = int(result.split(":")[1])
    assert count >= 1

    audit_rows = await _fetch_audit_rows(async_session, "stuck_pushes.detected")
    assert len(audit_rows) >= 1
    latest = audit_rows[-1]
    assert latest.user_id is None
    assert latest.resource_type == "retention"
    md = latest.metadata_json
    assert md["count"] == count
    assert md["threshold_minutes"] == settings.stuck_push_minutes
    assert "detected_at" in md
    assert "stuck_pushes" in md
    assert isinstance(md["stuck_pushes"], list)
    assert any(s["push_id"] == str(stuck_id) for s in md["stuck_pushes"])
    assert all(s["push_id"] != str(fresh_id) for s in md["stuck_pushes"])

    await _delete_audit_rows(async_session, "stuck_pushes.detected")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_detect_stuck_pushes_wrapper_no_stuck_skips_audit(
    async_engine, async_session
):
    await _delete_audit_rows(async_session, "stuck_pushes.detected")

    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        conn.execute(
            "UPDATE pushes SET updated_at = now() "
            "WHERE status IN ('pending', 'processing')"
        )

    result = await detect_stuck_pushes(_ctx())
    assert result == "stuck:0"

    audit_rows = await _fetch_audit_rows(async_session, "stuck_pushes.detected")
    assert audit_rows == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_detect_stuck_pushes_wrapper_truncates_metadata_at_50(
    async_engine, async_session
):
    await _delete_audit_rows(async_session, "stuck_pushes.detected")

    user_id, ws_id = _seed_user_and_workspace("dspT")
    stuck_minutes = settings.stuck_push_minutes + 60
    inserted_ids: list[uuid.UUID] = []
    for _ in range(60):
        pid = _insert_push(
            workspace_id=ws_id,
            user_id=user_id,
            status="processing",
            updated_minutes_ago=stuck_minutes,
        )
        inserted_ids.append(pid)

    result = await detect_stuck_pushes(_ctx())
    count = int(result.split(":")[1])
    assert count >= 60

    audit_rows = await _fetch_audit_rows(async_session, "stuck_pushes.detected")
    assert len(audit_rows) >= 1
    md = audit_rows[-1].metadata_json
    assert md["count"] == count
    assert md["truncated"] is True
    assert len(md["stuck_pushes"]) == 50

    await _delete_audit_rows(async_session, "stuck_pushes.detected")
