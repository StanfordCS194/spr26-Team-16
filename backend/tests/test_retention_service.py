"""Integration tests for the retention service (services/retention.py).

These tests exercise every public _impl function in the retention module against
a live Postgres + pgvector instance, validating cutoff arithmetic, status filters,
cascade deletion behaviour, storage-blob coordination, GDPR-style user-deletion,
and the dry-run aggregator.

All tests are marked ``integration`` because they require the conftest-managed
schema + fixture data. Each test creates its own user/workspace/push graph with
fresh uuid7() identifiers and runs inside a transaction that is rolled back at
the end, so seed data and other tests are unaffected.

Time-travel is achieved by inserting rows normally (the server_default fills
created_at/updated_at with NOW()) and then UPDATEing the timestamp columns to a
backdated, timezone-aware datetime via direct SQL. The retention impls accept an
explicit ``now=`` kwarg so cutoffs are deterministic.
"""

from __future__ import annotations

import hashlib
import uuid
from datetime import datetime, timedelta, timezone
from typing import AsyncIterator

import pytest
import pytest_asyncio
from sqlalchemy import select, text, update
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from contexthub_backend.config import settings
from contexthub_backend.db.models import (
    ApiToken,
    AuditLog,
    Profile,
    Pull,
    Push,
    PushTag,
    Summary,
    SummaryEmbedding,
    SummaryFeedback,
    Tag,
    Transcript,
    Workspace,
)
from contexthub_backend.db.short_id import uuid7
from contexthub_backend.services.retention import (
    PurgeReport,
    StuckPushReport,
    cascade_delete_user_impl,
    detect_stuck_pushes_impl,
    dry_run_all_impl,
    mark_stuck_pushes_failed_impl,
    purge_audit_log_impl,
    purge_failed_pushes_impl,
    purge_revoked_tokens_impl,
    purge_soft_deleted_pushes_impl,
)


pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Async engine / session fixtures
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture(scope="session")
async def async_engine(db_engine):
    engine = create_async_engine(settings.async_database_url, pool_pre_ping=True)
    yield engine
    await engine.dispose()


@pytest_asyncio.fixture
async def async_session(async_engine) -> AsyncIterator[AsyncSession]:
    """Function-scoped AsyncSession that rolls back at the end of the test.

    All retention impls run inside this single transaction so the database is
    untouched between tests.
    """
    Sessionmaker = async_sessionmaker(async_engine, expire_on_commit=False)
    async with Sessionmaker() as session:
        try:
            yield session
        finally:
            await session.rollback()
            await session.close()


# ---------------------------------------------------------------------------
# Fake storage that records delete calls
# ---------------------------------------------------------------------------


class FakeStorage:
    """Drop-in replacement for TranscriptStorageService used by retention.

    Records every deleted_paths entry and lets the test choose whether to raise
    on a particular path (to validate the best-effort blob-purge contract).
    """

    def __init__(self, *, raise_on: set[str] | None = None) -> None:
        self.deleted_paths: list[str] = []
        self.loaded_paths: list[str] = []
        self.stored: list[tuple[str, str]] = []
        self._raise_on = raise_on or set()

    async def delete_transcript(self, storage_path: str) -> None:
        if storage_path in self._raise_on:
            raise RuntimeError(f"simulated storage failure for {storage_path}")
        self.deleted_paths.append(storage_path)

    async def load_transcript(self, storage_path: str):  # pragma: no cover - stub
        self.loaded_paths.append(storage_path)
        return None

    async def store_transcript(self, **kwargs):  # pragma: no cover - stub
        self.stored.append(("store", str(kwargs)))
        return None


# ---------------------------------------------------------------------------
# Helpers — create users/workspaces/pushes inline so seed data isn't disturbed
# ---------------------------------------------------------------------------


async def _make_user(session: AsyncSession) -> uuid.UUID:
    uid = uuid7()
    email = f"{str(uid).replace('-', '')[:16]}@retention-test.local"
    await session.execute(
        text(
            "INSERT INTO auth.users (id, email) VALUES (:id, :email) "
            "ON CONFLICT (id) DO NOTHING"
        ),
        {"id": str(uid), "email": email},
    )
    return uid


async def _make_workspace(session: AsyncSession, user_id: uuid.UUID) -> Workspace:
    ws = Workspace(
        id=uuid7(),
        user_id=user_id,
        name=f"ws-{uuid.uuid4().hex[:8]}",
        slug=f"slug-{uuid.uuid4().hex[:10]}",
    )
    session.add(ws)
    await session.flush()
    return ws


async def _make_push(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    workspace_id: uuid.UUID,
    status: str = "pending",
    deleted_at: datetime | None = None,
    failure_reason: str | None = None,
    title: str | None = None,
) -> Push:
    push = Push(
        id=uuid7(),
        workspace_id=workspace_id,
        user_id=user_id,
        source_platform="claude_ai",
        interchange_version="ch.v0.1",
        status=status,
        title=title or f"push-{uuid.uuid4().hex[:6]}",
        idempotency_key=str(uuid.uuid4()),
        failure_reason=failure_reason,
        deleted_at=deleted_at,
    )
    session.add(push)
    await session.flush()
    return push


async def _make_transcript(
    session: AsyncSession, *, push_id: uuid.UUID, storage_path: str
) -> Transcript:
    tr = Transcript(
        push_id=push_id,
        storage_path=storage_path,
        sha256=hashlib.sha256(storage_path.encode()).hexdigest(),
        size_bytes=4096,
        message_count=8,
    )
    session.add(tr)
    await session.flush()
    return tr


async def _make_summary(session: AsyncSession, *, push_id: uuid.UUID) -> Summary:
    s = Summary(
        id=uuid7(),
        push_id=push_id,
        layer="summary",
        content_json={"text": "hello"},
        content_markdown="hello",
        model="claude-haiku-4-5",
        prompt_version="summarize_v1.0",
    )
    session.add(s)
    await session.flush()
    return s


async def _make_embedding(session: AsyncSession, *, summary_id: uuid.UUID) -> None:
    emb = SummaryEmbedding(
        summary_id=summary_id,
        embedding=[0.0] * 1024,
        embedding_model="voyage-3-large",
    )
    session.add(emb)
    await session.flush()


async def _make_tag_and_link(
    session: AsyncSession, *, workspace_id: uuid.UUID, push_id: uuid.UUID
) -> Tag:
    tag = Tag(
        id=uuid7(),
        workspace_id=workspace_id,
        name=f"tag-{uuid.uuid4().hex[:6]}",
        slug=f"slug-{uuid.uuid4().hex[:10]}",
    )
    session.add(tag)
    await session.flush()
    session.add(PushTag(push_id=push_id, tag_id=tag.id))
    await session.flush()
    return tag


async def _backdate_push_deleted_at(
    session: AsyncSession, push_id: uuid.UUID, when: datetime
) -> None:
    await session.execute(
        update(Push).where(Push.id == push_id).values(deleted_at=when)
    )


async def _backdate_push_created_at(
    session: AsyncSession, push_id: uuid.UUID, when: datetime
) -> None:
    await session.execute(
        update(Push).where(Push.id == push_id).values(created_at=when)
    )


async def _backdate_push_updated_at(
    session: AsyncSession, push_id: uuid.UUID, when: datetime
) -> None:
    await session.execute(
        update(Push).where(Push.id == push_id).values(updated_at=when)
    )


async def _backdate_audit_created_at(
    session: AsyncSession, audit_id: uuid.UUID, when: datetime
) -> None:
    await session.execute(
        update(AuditLog).where(AuditLog.id == audit_id).values(created_at=when)
    )


async def _backdate_token_revoked_at(
    session: AsyncSession, token_id: uuid.UUID, when: datetime | None
) -> None:
    await session.execute(
        update(ApiToken).where(ApiToken.id == token_id).values(revoked_at=when)
    )


async def _make_audit(
    session: AsyncSession, *, user_id: uuid.UUID, action: str = "test.event"
) -> AuditLog:
    row = AuditLog(
        id=uuid7(),
        user_id=user_id,
        action=action,
        resource_type="push",
        resource_id=str(uuid.uuid4()),
    )
    session.add(row)
    await session.flush()
    return row


async def _make_token(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    revoked_at: datetime | None = None,
    name: str | None = None,
) -> ApiToken:
    tok = ApiToken(
        id=uuid7(),
        user_id=user_id,
        name=name or f"token-{uuid.uuid4().hex[:6]}",
        token_hash=hashlib.sha256(uuid.uuid4().bytes).hexdigest(),
        scopes=["push:write"],
        revoked_at=revoked_at,
    )
    session.add(tok)
    await session.flush()
    return tok


async def _push_exists(session: AsyncSession, push_id: uuid.UUID) -> bool:
    res = await session.execute(select(Push.id).where(Push.id == push_id))
    return res.first() is not None


# ---------------------------------------------------------------------------
# 1. purge_soft_deleted_pushes_impl
# ---------------------------------------------------------------------------


async def test_purge_soft_deleted_pushes_deletes_old_row(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(async_session, user_id=user_id, workspace_id=ws.id)

    now = datetime.now(timezone.utc)
    old = now - timedelta(days=settings.retention_soft_delete_days + 5)
    await _backdate_push_deleted_at(async_session, push.id, old)

    report = await purge_soft_deleted_pushes_impl(async_session, now=now)

    assert isinstance(report, PurgeReport)
    assert report.job == "purge_soft_deleted_pushes"
    assert report.rows_by_table.get("pushes", 0) >= 1
    assert report.started_at is not None
    assert report.finished_at is not None
    assert not await _push_exists(async_session, push.id)


async def test_purge_soft_deleted_pushes_preserves_recent_row(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(async_session, user_id=user_id, workspace_id=ws.id)

    now = datetime.now(timezone.utc)
    recent = now - timedelta(days=1)
    await _backdate_push_deleted_at(async_session, push.id, recent)

    report = await purge_soft_deleted_pushes_impl(async_session, now=now)
    assert report.rows_by_table.get("pushes", 0) == 0
    assert await _push_exists(async_session, push.id)


async def test_purge_soft_deleted_pushes_skips_non_deleted(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(async_session, user_id=user_id, workspace_id=ws.id)

    now = datetime.now(timezone.utc)
    report = await purge_soft_deleted_pushes_impl(async_session, now=now)
    assert report.rows_by_table.get("pushes", 0) == 0
    assert await _push_exists(async_session, push.id)


async def test_purge_soft_deleted_pushes_boundary_is_strict_less_than(
    async_session: AsyncSession,
):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(async_session, user_id=user_id, workspace_id=ws.id)

    now = datetime.now(timezone.utc)
    # deleted_at is exactly cutoff (not strictly less than) → preserved
    cutoff = now - timedelta(days=settings.retention_soft_delete_days)
    await _backdate_push_deleted_at(async_session, push.id, cutoff)

    report = await purge_soft_deleted_pushes_impl(async_session, now=now)
    assert report.rows_by_table.get("pushes", 0) == 0
    assert await _push_exists(async_session, push.id)


async def test_purge_soft_deleted_pushes_custom_days_override(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(async_session, user_id=user_id, workspace_id=ws.id)

    now = datetime.now(timezone.utc)
    # 2 days old: not deletable at default 30, deletable at days=1
    await _backdate_push_deleted_at(async_session, push.id, now - timedelta(days=2))

    report_default = await purge_soft_deleted_pushes_impl(async_session, now=now)
    assert report_default.rows_by_table.get("pushes", 0) == 0
    assert await _push_exists(async_session, push.id)

    report_override = await purge_soft_deleted_pushes_impl(
        async_session, now=now, days=1
    )
    assert report_override.rows_by_table.get("pushes", 0) == 1
    assert not await _push_exists(async_session, push.id)


async def test_purge_soft_deleted_pushes_collects_storage_paths_and_calls_delete(
    async_session: AsyncSession,
):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="ready"
    )
    expected_path = f"transcripts/{user_id}/{push.id}.json"
    await _make_transcript(async_session, push_id=push.id, storage_path=expected_path)

    now = datetime.now(timezone.utc)
    await _backdate_push_deleted_at(
        async_session,
        push.id,
        now - timedelta(days=settings.retention_soft_delete_days + 1),
    )

    storage = FakeStorage()
    report = await purge_soft_deleted_pushes_impl(
        async_session, storage=storage, now=now
    )

    assert expected_path in report.storage_paths
    assert expected_path in storage.deleted_paths
    assert not await _push_exists(async_session, push.id)


async def test_purge_soft_deleted_pushes_storage_failure_does_not_abort_db_delete(
    async_session: AsyncSession,
):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="ready"
    )
    bad_path = f"transcripts/{user_id}/{push.id}.json"
    await _make_transcript(async_session, push_id=push.id, storage_path=bad_path)

    now = datetime.now(timezone.utc)
    await _backdate_push_deleted_at(
        async_session,
        push.id,
        now - timedelta(days=settings.retention_soft_delete_days + 5),
    )

    storage = FakeStorage(raise_on={bad_path})
    report = await purge_soft_deleted_pushes_impl(
        async_session, storage=storage, now=now
    )

    assert any("storage_delete_failed" in n for n in report.notes)
    assert report.rows_by_table.get("pushes", 0) >= 1
    assert not await _push_exists(async_session, push.id)


async def test_purge_soft_deleted_pushes_mixed_set(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    now = datetime.now(timezone.utc)

    old1 = await _make_push(async_session, user_id=user_id, workspace_id=ws.id)
    old2 = await _make_push(async_session, user_id=user_id, workspace_id=ws.id)
    recent = await _make_push(async_session, user_id=user_id, workspace_id=ws.id)
    never = await _make_push(async_session, user_id=user_id, workspace_id=ws.id)

    await _backdate_push_deleted_at(
        async_session,
        old1.id,
        now - timedelta(days=settings.retention_soft_delete_days + 1),
    )
    await _backdate_push_deleted_at(
        async_session,
        old2.id,
        now - timedelta(days=settings.retention_soft_delete_days + 100),
    )
    await _backdate_push_deleted_at(
        async_session, recent.id, now - timedelta(days=1)
    )
    # `never` keeps deleted_at = NULL

    report = await purge_soft_deleted_pushes_impl(async_session, now=now)

    assert report.rows_by_table.get("pushes", 0) == 2
    assert not await _push_exists(async_session, old1.id)
    assert not await _push_exists(async_session, old2.id)
    assert await _push_exists(async_session, recent.id)
    assert await _push_exists(async_session, never.id)


async def test_purge_soft_deleted_pushes_cascades_summaries_and_embeddings(
    async_session: AsyncSession,
):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="ready"
    )
    summary = await _make_summary(async_session, push_id=push.id)
    await _make_embedding(async_session, summary_id=summary.id)
    await _make_tag_and_link(async_session, workspace_id=ws.id, push_id=push.id)
    await _make_transcript(
        async_session,
        push_id=push.id,
        storage_path=f"transcripts/{user_id}/{push.id}.json",
    )

    now = datetime.now(timezone.utc)
    await _backdate_push_deleted_at(
        async_session,
        push.id,
        now - timedelta(days=settings.retention_soft_delete_days + 1),
    )

    await purge_soft_deleted_pushes_impl(async_session, now=now)

    assert not await _push_exists(async_session, push.id)
    s_rows = (
        await async_session.execute(
            select(Summary.id).where(Summary.push_id == push.id)
        )
    ).all()
    assert s_rows == []
    e_rows = (
        await async_session.execute(
            select(SummaryEmbedding.summary_id).where(
                SummaryEmbedding.summary_id == summary.id
            )
        )
    ).all()
    assert e_rows == []
    pt_rows = (
        await async_session.execute(
            select(PushTag.push_id).where(PushTag.push_id == push.id)
        )
    ).all()
    assert pt_rows == []
    tr_rows = (
        await async_session.execute(
            select(Transcript.push_id).where(Transcript.push_id == push.id)
        )
    ).all()
    assert tr_rows == []


async def test_purge_soft_deleted_pushes_empty_returns_clean_report(
    async_session: AsyncSession,
):
    # Restrict the query window to NOW-0 days so nothing in seed data matches —
    # by passing days=10_000 we make the cutoff far in the past and nothing
    # qualifies.
    now = datetime.now(timezone.utc)
    report = await purge_soft_deleted_pushes_impl(
        async_session, now=now, days=10_000
    )
    assert report.rows_deleted == 0
    assert report.rows_by_table == {}
    assert report.finished_at is not None
    assert report.started_at is not None


# ---------------------------------------------------------------------------
# 2. purge_failed_pushes_impl
# ---------------------------------------------------------------------------


async def test_purge_failed_pushes_deletes_old_failed(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(
        async_session,
        user_id=user_id,
        workspace_id=ws.id,
        status="failed",
        failure_reason="LLM JSON parse error",
    )
    now = datetime.now(timezone.utc)
    await _backdate_push_created_at(
        async_session,
        push.id,
        now - timedelta(days=settings.retention_failed_push_days + 1),
    )

    report = await purge_failed_pushes_impl(async_session, now=now)
    assert report.rows_by_table.get("pushes", 0) >= 1
    assert not await _push_exists(async_session, push.id)


async def test_purge_failed_pushes_preserves_recent(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="failed"
    )
    now = datetime.now(timezone.utc)
    await _backdate_push_created_at(
        async_session, push.id, now - timedelta(days=1)
    )

    report = await purge_failed_pushes_impl(async_session, now=now)
    assert report.rows_by_table.get("pushes", 0) == 0
    assert await _push_exists(async_session, push.id)


@pytest.mark.parametrize("status", ["ready", "processing", "pending"])
async def test_purge_failed_pushes_status_filter(
    async_session: AsyncSession, status: str
):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status=status
    )
    now = datetime.now(timezone.utc)
    await _backdate_push_created_at(
        async_session,
        push.id,
        now - timedelta(days=settings.retention_failed_push_days + 30),
    )

    report = await purge_failed_pushes_impl(async_session, now=now)
    assert report.rows_by_table.get("pushes", 0) == 0
    assert await _push_exists(async_session, push.id)


async def test_purge_failed_pushes_custom_days_override(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="failed"
    )
    now = datetime.now(timezone.utc)
    await _backdate_push_created_at(
        async_session, push.id, now - timedelta(days=2)
    )

    default_report = await purge_failed_pushes_impl(async_session, now=now)
    assert default_report.rows_by_table.get("pushes", 0) == 0
    assert await _push_exists(async_session, push.id)

    override_report = await purge_failed_pushes_impl(
        async_session, now=now, days=1
    )
    assert override_report.rows_by_table.get("pushes", 0) == 1
    assert not await _push_exists(async_session, push.id)


async def test_purge_failed_pushes_cascades_summaries(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="failed"
    )
    summary = await _make_summary(async_session, push_id=push.id)
    await _make_tag_and_link(async_session, workspace_id=ws.id, push_id=push.id)

    now = datetime.now(timezone.utc)
    await _backdate_push_created_at(
        async_session,
        push.id,
        now - timedelta(days=settings.retention_failed_push_days + 1),
    )

    await purge_failed_pushes_impl(async_session, now=now)

    assert not await _push_exists(async_session, push.id)
    s = (
        await async_session.execute(
            select(Summary.id).where(Summary.id == summary.id)
        )
    ).all()
    assert s == []


async def test_purge_failed_pushes_collects_storage_path(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="failed"
    )
    sp = f"transcripts/{user_id}/{push.id}.json"
    await _make_transcript(async_session, push_id=push.id, storage_path=sp)

    now = datetime.now(timezone.utc)
    await _backdate_push_created_at(
        async_session,
        push.id,
        now - timedelta(days=settings.retention_failed_push_days + 1),
    )

    storage = FakeStorage()
    report = await purge_failed_pushes_impl(
        async_session, now=now, storage=storage
    )
    assert sp in report.storage_paths
    assert sp in storage.deleted_paths


# ---------------------------------------------------------------------------
# 3. purge_audit_log_impl
# ---------------------------------------------------------------------------


async def test_purge_audit_log_deletes_old_rows(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    row = await _make_audit(async_session, user_id=user_id, action="ret.test.old")
    now = datetime.now(timezone.utc)
    await _backdate_audit_created_at(
        async_session,
        row.id,
        now - timedelta(days=settings.retention_audit_log_days + 1),
    )

    report = await purge_audit_log_impl(async_session, now=now)
    assert report.rows_by_table.get("audit_log", 0) >= 1

    res = await async_session.execute(
        select(AuditLog.id).where(AuditLog.id == row.id)
    )
    assert res.first() is None


async def test_purge_audit_log_preserves_recent(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    row = await _make_audit(async_session, user_id=user_id, action="ret.test.recent")
    now = datetime.now(timezone.utc)
    await _backdate_audit_created_at(async_session, row.id, now - timedelta(days=1))

    await purge_audit_log_impl(async_session, now=now)

    res = await async_session.execute(
        select(AuditLog.id).where(AuditLog.id == row.id)
    )
    assert res.first() is not None


async def test_purge_audit_log_boundary_strict_less_than(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    row = await _make_audit(async_session, user_id=user_id, action="ret.test.boundary")
    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(days=settings.retention_audit_log_days)
    await _backdate_audit_created_at(async_session, row.id, cutoff)

    await purge_audit_log_impl(async_session, now=now)

    res = await async_session.execute(
        select(AuditLog.id).where(AuditLog.id == row.id)
    )
    assert res.first() is not None


async def test_purge_audit_log_empty_case(async_session: AsyncSession):
    now = datetime.now(timezone.utc)
    report = await purge_audit_log_impl(async_session, now=now, days=10_000)
    assert report.rows_deleted == 0
    assert report.finished_at is not None


async def test_purge_audit_log_custom_days_override(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    row = await _make_audit(async_session, user_id=user_id, action="ret.test.override")
    now = datetime.now(timezone.utc)
    await _backdate_audit_created_at(async_session, row.id, now - timedelta(days=2))

    default_report = await purge_audit_log_impl(async_session, now=now)
    res_after_default = await async_session.execute(
        select(AuditLog.id).where(AuditLog.id == row.id)
    )
    assert res_after_default.first() is not None
    assert default_report.rows_by_table.get("audit_log", 0) >= 0  # no precise count

    override_report = await purge_audit_log_impl(async_session, now=now, days=1)
    assert override_report.rows_by_table.get("audit_log", 0) >= 1
    res_after_override = await async_session.execute(
        select(AuditLog.id).where(AuditLog.id == row.id)
    )
    assert res_after_override.first() is None


# ---------------------------------------------------------------------------
# 4. purge_revoked_tokens_impl
# ---------------------------------------------------------------------------


async def test_purge_revoked_tokens_deletes_old_revoked(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    tok = await _make_token(async_session, user_id=user_id)
    now = datetime.now(timezone.utc)
    await _backdate_token_revoked_at(
        async_session,
        tok.id,
        now - timedelta(days=settings.retention_revoked_token_days + 1),
    )

    report = await purge_revoked_tokens_impl(async_session, now=now)
    assert report.rows_by_table.get("api_tokens", 0) >= 1

    res = await async_session.execute(
        select(ApiToken.id).where(ApiToken.id == tok.id)
    )
    assert res.first() is None


async def test_purge_revoked_tokens_preserves_active(async_session: AsyncSession):
    """Active token (revoked_at IS NULL) is preserved no matter how old."""
    user_id = await _make_user(async_session)
    tok = await _make_token(async_session, user_id=user_id, revoked_at=None)

    now = datetime.now(timezone.utc)
    await async_session.execute(
        update(ApiToken)
        .where(ApiToken.id == tok.id)
        .values(created_at=now - timedelta(days=10_000))
    )

    report = await purge_revoked_tokens_impl(async_session, now=now, days=1)
    res = await async_session.execute(
        select(ApiToken.id).where(ApiToken.id == tok.id)
    )
    assert res.first() is not None
    # The active token must not be counted in the report.
    assert report.rows_by_table.get("api_tokens", 0) == 0


async def test_purge_revoked_tokens_preserves_recent_revocation(
    async_session: AsyncSession,
):
    user_id = await _make_user(async_session)
    tok = await _make_token(async_session, user_id=user_id)
    now = datetime.now(timezone.utc)
    await _backdate_token_revoked_at(async_session, tok.id, now - timedelta(days=1))

    await purge_revoked_tokens_impl(async_session, now=now)

    res = await async_session.execute(
        select(ApiToken.id).where(ApiToken.id == tok.id)
    )
    assert res.first() is not None


async def test_purge_revoked_tokens_custom_days_override(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    tok = await _make_token(async_session, user_id=user_id)
    now = datetime.now(timezone.utc)
    await _backdate_token_revoked_at(async_session, tok.id, now - timedelta(days=2))

    default_report = await purge_revoked_tokens_impl(async_session, now=now)
    assert default_report.rows_by_table.get("api_tokens", 0) == 0

    override_report = await purge_revoked_tokens_impl(
        async_session, now=now, days=1
    )
    assert override_report.rows_by_table.get("api_tokens", 0) == 1
    res = await async_session.execute(
        select(ApiToken.id).where(ApiToken.id == tok.id)
    )
    assert res.first() is None


# ---------------------------------------------------------------------------
# 5. detect_stuck_pushes_impl
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("status", ["pending", "processing"])
async def test_detect_stuck_pushes_returns_old_pending_or_processing(
    async_session: AsyncSession, status: str
):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status=status
    )
    now = datetime.now(timezone.utc)
    minutes = settings.stuck_push_minutes
    await _backdate_push_updated_at(
        async_session, push.id, now - timedelta(minutes=minutes + 5)
    )

    out = await detect_stuck_pushes_impl(async_session, now=now)

    matching = [r for r in out if r.push_id == push.id]
    assert matching, f"expected stuck report for {status} push"
    rep = matching[0]
    assert rep.push_id == push.id
    assert rep.user_id == user_id
    assert rep.workspace_id == ws.id
    assert rep.status == status
    assert rep.minutes_stuck >= minutes


@pytest.mark.parametrize("status", ["ready", "failed"])
async def test_detect_stuck_pushes_excludes_terminal_status(
    async_session: AsyncSession, status: str
):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status=status
    )
    now = datetime.now(timezone.utc)
    await _backdate_push_updated_at(
        async_session, push.id, now - timedelta(minutes=10_000)
    )

    out = await detect_stuck_pushes_impl(async_session, now=now)
    assert all(r.push_id != push.id for r in out)


async def test_detect_stuck_pushes_threshold_override(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="processing"
    )
    now = datetime.now(timezone.utc)
    # 3 minutes old: not stuck at 5min default, stuck at 1min override
    await _backdate_push_updated_at(
        async_session, push.id, now - timedelta(minutes=3)
    )

    default_out = await detect_stuck_pushes_impl(async_session, now=now)
    assert all(r.push_id != push.id for r in default_out)

    override_out = await detect_stuck_pushes_impl(
        async_session, now=now, minutes=1
    )
    assert any(r.push_id == push.id for r in override_out)


async def test_detect_stuck_pushes_minutes_stuck_value(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="processing"
    )
    now = datetime.now(timezone.utc)
    await _backdate_push_updated_at(
        async_session, push.id, now - timedelta(minutes=42)
    )

    out = await detect_stuck_pushes_impl(async_session, now=now, minutes=10)
    matching = [r for r in out if r.push_id == push.id]
    assert matching
    assert matching[0].minutes_stuck >= 42 - 1  # tolerate floor rounding
    assert matching[0].minutes_stuck <= 43


async def test_detect_stuck_pushes_returns_empty_when_none_stuck(
    async_session: AsyncSession,
):
    now = datetime.now(timezone.utc)
    # Ridiculously high threshold -> nothing qualifies
    out = await detect_stuck_pushes_impl(async_session, now=now, minutes=1_000_000_000)
    assert out == []


async def test_detect_stuck_pushes_returns_multiple(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    p1 = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="pending"
    )
    p2 = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="processing"
    )
    now = datetime.now(timezone.utc)
    await _backdate_push_updated_at(
        async_session, p1.id, now - timedelta(minutes=30)
    )
    await _backdate_push_updated_at(
        async_session, p2.id, now - timedelta(minutes=45)
    )

    out = await detect_stuck_pushes_impl(async_session, now=now, minutes=10)
    ids = {r.push_id for r in out}
    assert p1.id in ids
    assert p2.id in ids
    assert all(isinstance(r, StuckPushReport) for r in out)


# ---------------------------------------------------------------------------
# 6. mark_stuck_pushes_failed_impl
# ---------------------------------------------------------------------------


async def test_mark_stuck_pushes_failed_flips_status_with_reason(
    async_session: AsyncSession,
):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    stuck = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="processing"
    )
    fresh = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="processing"
    )
    now = datetime.now(timezone.utc)
    await _backdate_push_updated_at(
        async_session, stuck.id, now - timedelta(minutes=120)
    )
    # leave `fresh` with NOW updated_at -> not stuck

    report = await mark_stuck_pushes_failed_impl(
        async_session,
        now=now,
        minutes=10,
        failure_reason="custom_reason_xyz",
    )

    assert report.rows_by_table.get("pushes", 0) >= 1

    stuck_row = (
        await async_session.execute(select(Push).where(Push.id == stuck.id))
    ).scalar_one()
    assert stuck_row.status == "failed"
    assert stuck_row.failure_reason == "custom_reason_xyz"

    fresh_row = (
        await async_session.execute(select(Push).where(Push.id == fresh.id))
    ).scalar_one()
    assert fresh_row.status == "processing"
    assert fresh_row.failure_reason is None


async def test_mark_stuck_pushes_failed_idempotent(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    stuck = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="pending"
    )
    now = datetime.now(timezone.utc)
    await _backdate_push_updated_at(
        async_session, stuck.id, now - timedelta(minutes=120)
    )

    first = await mark_stuck_pushes_failed_impl(async_session, now=now, minutes=10)
    second = await mark_stuck_pushes_failed_impl(async_session, now=now, minutes=10)

    assert first.rows_by_table.get("pushes", 0) >= 1
    assert second.rows_by_table.get("pushes", 0) == 0

    row = (
        await async_session.execute(select(Push).where(Push.id == stuck.id))
    ).scalar_one()
    assert row.status == "failed"


# ---------------------------------------------------------------------------
# 7. cascade_delete_user_impl
# ---------------------------------------------------------------------------


async def _seed_full_user(async_session: AsyncSession) -> dict:
    """Build a full graph of rows owned by one user so the cascade test can
    assert that every table is fully drained for that user_id.
    """
    user_id = await _make_user(async_session)
    ws1 = await _make_workspace(async_session, user_id)
    ws2 = await _make_workspace(async_session, user_id)

    push1 = await _make_push(
        async_session, user_id=user_id, workspace_id=ws1.id, status="ready"
    )
    push2 = await _make_push(
        async_session, user_id=user_id, workspace_id=ws1.id, status="failed"
    )
    push3 = await _make_push(
        async_session, user_id=user_id, workspace_id=ws2.id, status="ready"
    )

    summary1 = await _make_summary(async_session, push_id=push1.id)
    await _make_embedding(async_session, summary_id=summary1.id)
    summary2 = await _make_summary(async_session, push_id=push3.id)

    tag1 = await _make_tag_and_link(
        async_session, workspace_id=ws1.id, push_id=push1.id
    )
    tag2 = await _make_tag_and_link(
        async_session, workspace_id=ws2.id, push_id=push3.id
    )

    paths = []
    for p in (push1, push2, push3):
        sp = f"transcripts/{user_id}/{p.id}.json"
        await _make_transcript(async_session, push_id=p.id, storage_path=sp)
        paths.append(sp)

    fb = SummaryFeedback(
        id=uuid7(),
        summary_id=summary1.id,
        user_id=user_id,
        score=4,
        comment="good",
    )
    async_session.add(fb)

    pull = Pull(
        id=uuid7(),
        user_id=user_id,
        target_platform="claude_ai",
        origin="dashboard",
        resolution="summary",
        push_ids=[str(push1.id)],
        workspace_ids=[str(ws1.id)],
        token_estimate=100,
    )
    async_session.add(pull)

    tok = await _make_token(async_session, user_id=user_id)
    profile = Profile(user_id=user_id, display_name="Test User")
    async_session.add(profile)

    audit_row = await _make_audit(async_session, user_id=user_id, action="cascade.test")

    await async_session.flush()

    return {
        "user_id": user_id,
        "workspaces": [ws1.id, ws2.id],
        "pushes": [push1.id, push2.id, push3.id],
        "summaries": [summary1.id, summary2.id],
        "tags": [tag1.id, tag2.id],
        "storage_paths": paths,
        "token_id": tok.id,
        "feedback_id": fb.id,
        "pull_id": pull.id,
        "audit_id": audit_row.id,
    }


async def test_cascade_delete_user_removes_all_user_data(async_session: AsyncSession):
    seed = await _seed_full_user(async_session)
    user_id = seed["user_id"]

    storage = FakeStorage()
    report = await cascade_delete_user_impl(
        async_session, user_id=user_id, storage=storage
    )

    assert report.job == "cascade_delete_user"
    assert report.rows_by_table.get("pushes", 0) >= 3
    assert report.rows_by_table.get("workspaces", 0) >= 2
    assert report.rows_by_table.get("api_tokens", 0) >= 1
    assert report.rows_by_table.get("profiles", 0) >= 1
    assert report.rows_by_table.get("pulls", 0) >= 1
    assert report.rows_by_table.get("summary_feedback", 0) >= 1
    assert report.rows_by_table.get("tags", 0) >= 2

    pushes_left = (
        await async_session.execute(select(Push.id).where(Push.user_id == user_id))
    ).all()
    assert pushes_left == []

    ws_left = (
        await async_session.execute(
            select(Workspace.id).where(Workspace.user_id == user_id)
        )
    ).all()
    assert ws_left == []

    tok_left = (
        await async_session.execute(
            select(ApiToken.id).where(ApiToken.user_id == user_id)
        )
    ).all()
    assert tok_left == []

    prof_left = (
        await async_session.execute(
            select(Profile.user_id).where(Profile.user_id == user_id)
        )
    ).all()
    assert prof_left == []

    pull_left = (
        await async_session.execute(select(Pull.id).where(Pull.user_id == user_id))
    ).all()
    assert pull_left == []

    fb_left = (
        await async_session.execute(
            select(SummaryFeedback.id).where(SummaryFeedback.user_id == user_id)
        )
    ).all()
    assert fb_left == []

    # Tags belonged to deleted workspaces -> hard-deleted by both the explicit
    # tags delete and the workspace cascade.
    for tid in seed["tags"]:
        rows = (
            await async_session.execute(select(Tag.id).where(Tag.id == tid))
        ).all()
        assert rows == []


async def test_cascade_delete_user_preserves_other_users(async_session: AsyncSession):
    target = await _seed_full_user(async_session)
    bystander = await _seed_full_user(async_session)

    target_id = target["user_id"]
    other_id = bystander["user_id"]

    other_pushes_before = len(
        (
            await async_session.execute(
                select(Push.id).where(Push.user_id == other_id)
            )
        ).all()
    )
    other_ws_before = len(
        (
            await async_session.execute(
                select(Workspace.id).where(Workspace.user_id == other_id)
            )
        ).all()
    )

    storage = FakeStorage()
    await cascade_delete_user_impl(
        async_session, user_id=target_id, storage=storage
    )

    other_pushes_after = len(
        (
            await async_session.execute(
                select(Push.id).where(Push.user_id == other_id)
            )
        ).all()
    )
    other_ws_after = len(
        (
            await async_session.execute(
                select(Workspace.id).where(Workspace.user_id == other_id)
            )
        ).all()
    )

    assert other_pushes_before == other_pushes_after
    assert other_ws_before == other_ws_after
    assert other_pushes_after >= 3
    assert other_ws_after >= 2

    # Only the target user's storage paths were deleted
    for sp in target["storage_paths"]:
        assert sp in storage.deleted_paths
    for sp in bystander["storage_paths"]:
        assert sp not in storage.deleted_paths


async def test_cascade_delete_user_collects_storage_paths(async_session: AsyncSession):
    seed = await _seed_full_user(async_session)
    storage = FakeStorage()

    report = await cascade_delete_user_impl(
        async_session, user_id=seed["user_id"], storage=storage
    )

    for sp in seed["storage_paths"]:
        assert sp in report.storage_paths
        assert sp in storage.deleted_paths
    assert len(storage.deleted_paths) >= len(seed["storage_paths"])


async def test_cascade_delete_user_anonymizes_audit_log(async_session: AsyncSession):
    seed = await _seed_full_user(async_session)

    await cascade_delete_user_impl(
        async_session, user_id=seed["user_id"], storage=FakeStorage()
    )

    row = (
        await async_session.execute(
            select(AuditLog).where(AuditLog.id == seed["audit_id"])
        )
    ).scalar_one()
    assert row.user_id is None
    assert row.action == "cascade.test"  # row itself preserved


async def test_cascade_delete_user_storage_failure_still_completes_db(
    async_session: AsyncSession,
):
    seed = await _seed_full_user(async_session)
    bad = seed["storage_paths"][0]
    storage = FakeStorage(raise_on={bad})

    report = await cascade_delete_user_impl(
        async_session, user_id=seed["user_id"], storage=storage
    )

    assert any("storage_delete_failed" in n for n in report.notes)
    pushes_left = (
        await async_session.execute(
            select(Push.id).where(Push.user_id == seed["user_id"])
        )
    ).all()
    assert pushes_left == []


async def test_cascade_delete_user_report_has_user_id_note(async_session: AsyncSession):
    seed = await _seed_full_user(async_session)
    report = await cascade_delete_user_impl(
        async_session, user_id=seed["user_id"], storage=FakeStorage()
    )
    assert any(f"user_id={seed['user_id']}" in n for n in report.notes)
    assert any("audit_log_anonymized=" in n for n in report.notes)


# ---------------------------------------------------------------------------
# 8. dry_run_all_impl
# ---------------------------------------------------------------------------


async def test_dry_run_all_returns_all_keys(async_session: AsyncSession):
    now = datetime.now(timezone.utc)
    out = await dry_run_all_impl(async_session, now=now)

    assert set(out.keys()) >= {
        "purge_soft_deleted_pushes",
        "purge_failed_pushes",
        "purge_audit_log",
        "purge_revoked_tokens",
        "stuck_pushes",
    }
    for k in (
        "purge_soft_deleted_pushes",
        "purge_failed_pushes",
        "purge_audit_log",
        "purge_revoked_tokens",
    ):
        assert "would_delete" in out[k]
        assert "cutoff" in out[k]
        # cutoff field must be parseable ISO timestamp
        datetime.fromisoformat(out[k]["cutoff"])
        assert "days" in out[k]
    assert "count" in out["stuck_pushes"]
    assert "threshold_minutes" in out["stuck_pushes"]


async def test_dry_run_all_does_not_modify_data(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    push_soft = await _make_push(async_session, user_id=user_id, workspace_id=ws.id)
    push_failed = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="failed"
    )
    audit_row = await _make_audit(async_session, user_id=user_id, action="dry.test")
    tok = await _make_token(async_session, user_id=user_id)

    now = datetime.now(timezone.utc)
    await _backdate_push_deleted_at(
        async_session,
        push_soft.id,
        now - timedelta(days=settings.retention_soft_delete_days + 1),
    )
    await _backdate_push_created_at(
        async_session,
        push_failed.id,
        now - timedelta(days=settings.retention_failed_push_days + 1),
    )
    await _backdate_audit_created_at(
        async_session,
        audit_row.id,
        now - timedelta(days=settings.retention_audit_log_days + 1),
    )
    await _backdate_token_revoked_at(
        async_session,
        tok.id,
        now - timedelta(days=settings.retention_revoked_token_days + 1),
    )

    def _row_count_query(target_table: str) -> str:
        return f"SELECT COUNT(*) FROM {target_table}"

    counts_before = {
        "pushes": (await async_session.execute(text(_row_count_query("pushes")))).scalar_one(),
        "audit_log": (
            await async_session.execute(text(_row_count_query("audit_log")))
        ).scalar_one(),
        "api_tokens": (
            await async_session.execute(text(_row_count_query("api_tokens")))
        ).scalar_one(),
    }

    await dry_run_all_impl(async_session, now=now)

    counts_after = {
        "pushes": (await async_session.execute(text(_row_count_query("pushes")))).scalar_one(),
        "audit_log": (
            await async_session.execute(text(_row_count_query("audit_log")))
        ).scalar_one(),
        "api_tokens": (
            await async_session.execute(text(_row_count_query("api_tokens")))
        ).scalar_one(),
    }

    assert counts_before == counts_after
    # And the rows we expected to still be there
    assert await _push_exists(async_session, push_soft.id)
    assert await _push_exists(async_session, push_failed.id)


async def test_dry_run_all_counts_match_real_purges(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)

    soft1 = await _make_push(async_session, user_id=user_id, workspace_id=ws.id)
    soft2 = await _make_push(async_session, user_id=user_id, workspace_id=ws.id)
    failed1 = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="failed"
    )
    audit_row = await _make_audit(async_session, user_id=user_id, action="match.test")
    tok = await _make_token(async_session, user_id=user_id)

    now = datetime.now(timezone.utc)
    for pid in (soft1.id, soft2.id):
        await _backdate_push_deleted_at(
            async_session,
            pid,
            now - timedelta(days=settings.retention_soft_delete_days + 1),
        )
    await _backdate_push_created_at(
        async_session,
        failed1.id,
        now - timedelta(days=settings.retention_failed_push_days + 1),
    )
    await _backdate_audit_created_at(
        async_session,
        audit_row.id,
        now - timedelta(days=settings.retention_audit_log_days + 1),
    )
    await _backdate_token_revoked_at(
        async_session,
        tok.id,
        now - timedelta(days=settings.retention_revoked_token_days + 1),
    )

    dry = await dry_run_all_impl(async_session, now=now)

    soft_pred = dry["purge_soft_deleted_pushes"]["would_delete"]
    failed_pred = dry["purge_failed_pushes"]["would_delete"]
    audit_pred = dry["purge_audit_log"]["would_delete"]
    token_pred = dry["purge_revoked_tokens"]["would_delete"]

    soft_real = await purge_soft_deleted_pushes_impl(async_session, now=now)
    failed_real = await purge_failed_pushes_impl(async_session, now=now)
    audit_real = await purge_audit_log_impl(async_session, now=now)
    token_real = await purge_revoked_tokens_impl(async_session, now=now)

    assert soft_real.rows_by_table.get("pushes", 0) == soft_pred
    assert failed_real.rows_by_table.get("pushes", 0) == failed_pred
    assert audit_real.rows_by_table.get("audit_log", 0) == audit_pred
    assert token_real.rows_by_table.get("api_tokens", 0) == token_pred


async def test_dry_run_all_stuck_count_matches_detect(async_session: AsyncSession):
    user_id = await _make_user(async_session)
    ws = await _make_workspace(async_session, user_id)
    p1 = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="processing"
    )
    p2 = await _make_push(
        async_session, user_id=user_id, workspace_id=ws.id, status="pending"
    )
    now = datetime.now(timezone.utc)
    await _backdate_push_updated_at(
        async_session,
        p1.id,
        now - timedelta(minutes=settings.stuck_push_minutes + 30),
    )
    await _backdate_push_updated_at(
        async_session,
        p2.id,
        now - timedelta(minutes=settings.stuck_push_minutes + 30),
    )

    dry = await dry_run_all_impl(async_session, now=now)
    detected = await detect_stuck_pushes_impl(async_session, now=now)

    assert dry["stuck_pushes"]["count"] == len(detected)
    assert dry["stuck_pushes"]["count"] >= 2
