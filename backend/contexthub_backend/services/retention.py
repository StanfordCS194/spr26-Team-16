"""Data retention service (ARCHITECTURE.md §13).

Pure-DB implementations of the retention purges and stuck-push detection.
The ARQ job wrappers in `jobs/tasks.py` import these and add transactional /
audit-log scaffolding.

Each `_impl` returns a `PurgeReport` describing what was deleted. Callers
emit observability events from the report; the impls themselves never call
out to logging or telemetry, which keeps them deterministic for tests.

Design notes:
- All time windows come from `settings.retention_*_days`. Tests pass an
  explicit `now` to make boundary cases reproducible.
- Hard deletes rely on the FK cascades declared in `db/models.py`. The
  retention job is responsible for non-cascading side effects: removing
  blob objects from Supabase Storage *before* the parent row goes away.
- Storage purges run before DB purges so a mid-run crash leaves orphaned
  rows (recoverable on next run) rather than orphaned blobs (permanent
  cost). The transcript blob path is reconstructable from
  `transcripts.storage_path`, so we capture that into `PurgeReport.storage_paths`
  before the DELETE.
- All queries are RLS-bypassing (run under the service role / postgres
  role); the worker never sets `app.current_user_id` for these.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Iterable

from sqlalchemy import and_, delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.config import settings
from contexthub_backend.db.models import (
    ApiToken,
    AuditLog,
    Profile,
    Pull,
    Push,
    SummaryFeedback,
    Tag,
    Transcript,
    Workspace,
)
from contexthub_backend.services.storage import TranscriptStorageService


# ---------------------------------------------------------------------------
# Reports
# ---------------------------------------------------------------------------


@dataclass(slots=True)
class PurgeReport:
    """Summary of one purge run, suitable for AuditLog + PostHog.

    Designed to be merged easily — `merge` lets the cascade-delete job
    aggregate per-table reports into a single receipt.
    """

    job: str
    rows_deleted: int = 0
    storage_paths: list[str] = field(default_factory=list)
    rows_by_table: dict[str, int] = field(default_factory=dict)
    started_at: datetime | None = None
    finished_at: datetime | None = None
    notes: list[str] = field(default_factory=list)

    def add_table(self, table: str, n: int) -> None:
        self.rows_by_table[table] = self.rows_by_table.get(table, 0) + n
        self.rows_deleted += n

    def merge(self, other: "PurgeReport") -> None:
        for tbl, n in other.rows_by_table.items():
            self.add_table(tbl, n)
        self.storage_paths.extend(other.storage_paths)
        self.notes.extend(other.notes)

    def to_dict(self) -> dict[str, object]:
        return {
            "job": self.job,
            "rows_deleted": self.rows_deleted,
            "rows_by_table": dict(self.rows_by_table),
            "storage_paths_purged": len(self.storage_paths),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "finished_at": self.finished_at.isoformat() if self.finished_at else None,
            "notes": list(self.notes),
        }


@dataclass(slots=True)
class StuckPushReport:
    """One row per stuck push. Returned as a list to the alerting layer."""

    push_id: uuid.UUID
    user_id: uuid.UUID
    workspace_id: uuid.UUID
    status: str
    minutes_stuck: int
    failure_reason: str | None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _now(now: datetime | None) -> datetime:
    return now or datetime.now(timezone.utc)


def _cutoff(days: int, now: datetime | None) -> datetime:
    return _now(now) - timedelta(days=days)


async def _delete_storage_blobs(
    storage: TranscriptStorageService | None,
    paths: Iterable[str],
    report: PurgeReport,
) -> None:
    """Best-effort blob purge. A failure logs into report.notes but doesn't
    abort the DB delete — orphaned blobs are addressed by the next run."""
    if storage is None:
        return
    for path in paths:
        try:
            await storage.delete_transcript(path)
        except Exception as exc:  # noqa: BLE001 — best-effort
            report.notes.append(f"storage_delete_failed:{path}:{exc!r}")


# ---------------------------------------------------------------------------
# Purge: soft-deleted pushes (30d default)
# ---------------------------------------------------------------------------


async def purge_soft_deleted_pushes_impl(
    session: AsyncSession,
    *,
    storage: TranscriptStorageService | None = None,
    now: datetime | None = None,
    days: int | None = None,
) -> PurgeReport:
    """Hard-delete pushes whose `deleted_at` is older than the retention window.

    Cascades (per FK ondelete) take care of summaries / embeddings / push_tags /
    push_relationships / transcripts row. We separately delete the transcript
    *blob* in Supabase Storage before the cascade fires so we never orphan
    storage objects.
    """
    report = PurgeReport(job="purge_soft_deleted_pushes")
    report.started_at = _now(now)
    cutoff = _cutoff(days if days is not None else settings.retention_soft_delete_days, now)

    push_ids_q = select(Push.id, Transcript.storage_path).join(
        Transcript, Transcript.push_id == Push.id, isouter=True
    ).where(
        and_(Push.deleted_at.is_not(None), Push.deleted_at < cutoff)
    )
    rows = (await session.execute(push_ids_q)).all()
    if not rows:
        report.finished_at = _now(now)
        return report

    push_ids = [row[0] for row in rows]
    storage_paths = [row[1] for row in rows if row[1]]
    report.storage_paths = storage_paths
    await _delete_storage_blobs(storage, storage_paths, report)

    res = await session.execute(delete(Push).where(Push.id.in_(push_ids)))
    report.add_table("pushes", res.rowcount or 0)
    report.finished_at = _now(now)
    return report


# ---------------------------------------------------------------------------
# Purge: failed pushes (7d default)
# ---------------------------------------------------------------------------


async def purge_failed_pushes_impl(
    session: AsyncSession,
    *,
    storage: TranscriptStorageService | None = None,
    now: datetime | None = None,
    days: int | None = None,
) -> PurgeReport:
    """Hard-delete pushes that have been in `failed` for the retention window."""
    report = PurgeReport(job="purge_failed_pushes")
    report.started_at = _now(now)
    cutoff = _cutoff(days if days is not None else settings.retention_failed_push_days, now)

    push_ids_q = select(Push.id, Transcript.storage_path).join(
        Transcript, Transcript.push_id == Push.id, isouter=True
    ).where(
        and_(Push.status == "failed", Push.created_at < cutoff)
    )
    rows = (await session.execute(push_ids_q)).all()
    if not rows:
        report.finished_at = _now(now)
        return report

    push_ids = [row[0] for row in rows]
    storage_paths = [row[1] for row in rows if row[1]]
    report.storage_paths = storage_paths
    await _delete_storage_blobs(storage, storage_paths, report)

    res = await session.execute(delete(Push).where(Push.id.in_(push_ids)))
    report.add_table("pushes", res.rowcount or 0)
    report.finished_at = _now(now)
    return report


# ---------------------------------------------------------------------------
# Purge: audit log (90d default)
# ---------------------------------------------------------------------------


async def purge_audit_log_impl(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    days: int | None = None,
) -> PurgeReport:
    """Drop audit_log rows older than the retention window.

    audit_log is append-only and large; we keep this query simple and rely
    on the `idx_audit_log_created_at` index added in migration 005.
    """
    report = PurgeReport(job="purge_audit_log")
    report.started_at = _now(now)
    cutoff = _cutoff(days if days is not None else settings.retention_audit_log_days, now)

    res = await session.execute(delete(AuditLog).where(AuditLog.created_at < cutoff))
    report.add_table("audit_log", res.rowcount or 0)
    report.finished_at = _now(now)
    return report


# ---------------------------------------------------------------------------
# Purge: revoked api tokens (1y default)
# ---------------------------------------------------------------------------


async def purge_revoked_tokens_impl(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    days: int | None = None,
) -> PurgeReport:
    """Drop api_tokens whose `revoked_at` is older than the retention window."""
    report = PurgeReport(job="purge_revoked_tokens")
    report.started_at = _now(now)
    cutoff = _cutoff(days if days is not None else settings.retention_revoked_token_days, now)

    res = await session.execute(
        delete(ApiToken).where(
            and_(ApiToken.revoked_at.is_not(None), ApiToken.revoked_at < cutoff)
        )
    )
    report.add_table("api_tokens", res.rowcount or 0)
    report.finished_at = _now(now)
    return report


# ---------------------------------------------------------------------------
# Stuck-push detection
# ---------------------------------------------------------------------------


async def detect_stuck_pushes_impl(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    minutes: int | None = None,
) -> list[StuckPushReport]:
    """Return pushes that have sat in pending/processing past the threshold.

    Detection only — alerting + auto-requeue are decisions for the caller
    (Sentry alert, admin endpoint).
    """
    threshold_minutes = minutes if minutes is not None else settings.stuck_push_minutes
    cutoff = _now(now) - timedelta(minutes=threshold_minutes)

    q = select(Push).where(
        and_(
            Push.status.in_(["pending", "processing"]),
            Push.updated_at < cutoff,
        )
    )
    rows = (await session.execute(q)).scalars().all()
    out: list[StuckPushReport] = []
    for p in rows:
        delta = _now(now) - p.updated_at
        out.append(
            StuckPushReport(
                push_id=p.id,
                user_id=p.user_id,
                workspace_id=p.workspace_id,
                status=p.status,
                minutes_stuck=int(delta.total_seconds() // 60),
                failure_reason=p.failure_reason,
            )
        )
    return out


async def mark_stuck_pushes_failed_impl(
    session: AsyncSession,
    *,
    now: datetime | None = None,
    minutes: int | None = None,
    failure_reason: str = "stuck_in_processing",
) -> PurgeReport:
    """Transition stuck pushes to `failed`. Used by the admin requeue flow
    (mark failed, then a separate enqueue brings them back as a fresh job)."""
    report = PurgeReport(job="mark_stuck_pushes_failed")
    report.started_at = _now(now)
    threshold_minutes = minutes if minutes is not None else settings.stuck_push_minutes
    cutoff = _now(now) - timedelta(minutes=threshold_minutes)

    res = await session.execute(
        update(Push)
        .where(
            and_(
                Push.status.in_(["pending", "processing"]),
                Push.updated_at < cutoff,
            )
        )
        .values(status="failed", failure_reason=failure_reason)
    )
    report.add_table("pushes", res.rowcount or 0)
    report.finished_at = _now(now)
    return report


# ---------------------------------------------------------------------------
# User-deletion cascade (GDPR)
# ---------------------------------------------------------------------------


async def cascade_delete_user_impl(
    session: AsyncSession,
    *,
    user_id: uuid.UUID,
    storage: TranscriptStorageService | None = None,
    now: datetime | None = None,
) -> PurgeReport:
    """Full purge of a single user's data. Called from `cascade_delete_user`
    ARQ job and the admin endpoint.

    Order of operations matters: we collect transcript paths *before* deleting
    pushes so the cascade doesn't take the rows out from under us. Then:
    1. Delete blobs in Storage.
    2. Delete pushes (cascades summaries, embeddings, push_tags, push_relationships, transcripts row).
    3. Delete tags (workspace-level, no FK to push).
    4. Delete workspaces.
    5. Delete pulls (own user_id FK).
    6. Delete summary_feedback rows (FK SET NULL keeps history but sets user to NULL — we hard delete to honor erasure).
    7. Delete api_tokens (cascade on auth.users.id will also handle this if Supabase deletes the auth.users row, but we do it explicitly so partial deletes stay consistent).
    8. Delete profile.
    9. Append a single AuditLog entry with the receipt.

    Note: auth.users itself is owned by Supabase. The caller is responsible for
    invoking Supabase's user-delete admin API after this returns successfully.
    """
    report = PurgeReport(job="cascade_delete_user")
    report.started_at = _now(now)
    report.notes.append(f"user_id={user_id}")

    # 1. Collect transcript paths
    paths_q = select(Transcript.storage_path).join(Push, Transcript.push_id == Push.id).where(
        Push.user_id == user_id
    )
    paths = [r[0] for r in (await session.execute(paths_q)).all() if r[0]]
    report.storage_paths = paths
    await _delete_storage_blobs(storage, paths, report)

    # 2. Pushes (cascades to summaries, embeddings, push_tags, push_relationships, transcripts)
    res = await session.execute(delete(Push).where(Push.user_id == user_id))
    report.add_table("pushes", res.rowcount or 0)

    # 3. Tags (workspace-level, deleted via workspace cascade below, but
    #    explicit so the receipt counts them).
    tag_res = await session.execute(
        delete(Tag).where(
            Tag.workspace_id.in_(
                select(Workspace.id).where(Workspace.user_id == user_id)
            )
        )
    )
    report.add_table("tags", tag_res.rowcount or 0)

    # 4. Workspaces
    ws_res = await session.execute(delete(Workspace).where(Workspace.user_id == user_id))
    report.add_table("workspaces", ws_res.rowcount or 0)

    # 5. Pulls
    pull_res = await session.execute(delete(Pull).where(Pull.user_id == user_id))
    report.add_table("pulls", pull_res.rowcount or 0)

    # 6. Summary feedback (the FK is ON DELETE SET NULL, so cascading a user
    #    deletion in auth.users would just null the column. For erasure we
    #    hard-delete instead).
    fb_res = await session.execute(
        delete(SummaryFeedback).where(SummaryFeedback.user_id == user_id)
    )
    report.add_table("summary_feedback", fb_res.rowcount or 0)

    # 7. API tokens
    tok_res = await session.execute(delete(ApiToken).where(ApiToken.user_id == user_id))
    report.add_table("api_tokens", tok_res.rowcount or 0)

    # 8. Profile
    prof_res = await session.execute(delete(Profile).where(Profile.user_id == user_id))
    report.add_table("profiles", prof_res.rowcount or 0)

    # 9. Audit log: keep prior entries for compliance investigation but null
    #    the user_id (FK is SET NULL). We don't delete past audit rows here —
    #    the audit-log purge handles age-based deletion separately.
    al_res = await session.execute(
        update(AuditLog).where(AuditLog.user_id == user_id).values(user_id=None)
    )
    report.notes.append(f"audit_log_anonymized={al_res.rowcount or 0}")

    report.finished_at = _now(now)
    return report


# ---------------------------------------------------------------------------
# Dry-run aggregator (for /v1/admin/retention/dry-run)
# ---------------------------------------------------------------------------


async def dry_run_all_impl(
    session: AsyncSession,
    *,
    now: datetime | None = None,
) -> dict[str, dict[str, object]]:
    """Count what each purge *would* delete without modifying anything.

    Used by the admin dry-run endpoint and the staging verification step
    called out in TODO.md:52.
    """
    out: dict[str, dict[str, object]] = {}

    soft_cutoff = _cutoff(settings.retention_soft_delete_days, now)
    soft_count = (
        await session.execute(
            select(Push.id).where(
                and_(Push.deleted_at.is_not(None), Push.deleted_at < soft_cutoff)
            )
        )
    ).all()
    out["purge_soft_deleted_pushes"] = {
        "would_delete": len(soft_count),
        "cutoff": soft_cutoff.isoformat(),
        "days": settings.retention_soft_delete_days,
    }

    failed_cutoff = _cutoff(settings.retention_failed_push_days, now)
    failed_count = (
        await session.execute(
            select(Push.id).where(
                and_(Push.status == "failed", Push.created_at < failed_cutoff)
            )
        )
    ).all()
    out["purge_failed_pushes"] = {
        "would_delete": len(failed_count),
        "cutoff": failed_cutoff.isoformat(),
        "days": settings.retention_failed_push_days,
    }

    audit_cutoff = _cutoff(settings.retention_audit_log_days, now)
    audit_count = (
        await session.execute(
            select(AuditLog.id).where(AuditLog.created_at < audit_cutoff)
        )
    ).all()
    out["purge_audit_log"] = {
        "would_delete": len(audit_count),
        "cutoff": audit_cutoff.isoformat(),
        "days": settings.retention_audit_log_days,
    }

    token_cutoff = _cutoff(settings.retention_revoked_token_days, now)
    token_count = (
        await session.execute(
            select(ApiToken.id).where(
                and_(ApiToken.revoked_at.is_not(None), ApiToken.revoked_at < token_cutoff)
            )
        )
    ).all()
    out["purge_revoked_tokens"] = {
        "would_delete": len(token_count),
        "cutoff": token_cutoff.isoformat(),
        "days": settings.retention_revoked_token_days,
    }

    stuck = await detect_stuck_pushes_impl(session, now=now)
    out["stuck_pushes"] = {
        "count": len(stuck),
        "threshold_minutes": settings.stuck_push_minutes,
    }

    return out
