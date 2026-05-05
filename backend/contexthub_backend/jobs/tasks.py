from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Any

from arq import Retry
from arq.cron import cron
from asyncpg.exceptions import DeadlockDetectedError
from sqlalchemy import select
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.auth.rls import apply_rls_context
from contexthub_backend.config import settings
from contexthub_backend.db.base import make_async_engine
from contexthub_backend.db.models import AuditLog, Push, Summary, Transcript
from contexthub_backend.providers import get_embedding_provider, get_llm_provider
from contexthub_backend.services.embeddings import embed_summary as embed_summary_service
from contexthub_backend.services.retention import (
    cascade_delete_user_impl,
    detect_stuck_pushes_impl,
    purge_audit_log_impl,
    purge_failed_pushes_impl,
    purge_revoked_tokens_impl,
    purge_soft_deleted_pushes_impl,
)
from contexthub_backend.services.storage import TranscriptStorageService
from contexthub_backend.services.summarizer import (
    summarize_push as summarize_push_service,
)

logger = logging.getLogger(__name__)


async def summarize_push(
    ctx: dict[str, Any],
    *,
    push_id: str,
    request_id: str,
    scrub_flags: list[str],
) -> str:
    engine = make_async_engine(settings.async_database_url)
    storage = TranscriptStorageService(bucket=settings.transcript_bucket)
    llm = get_llm_provider(
        mode="live" if (settings.ai_gateway_api_key or settings.anthropic_api_key) else "fake"
    )
    try:
        async with AsyncSession(engine) as session:
            async with session.begin():
                push = await session.get(Push, uuid.UUID(push_id))
                if push is None:
                    return "missing_push"
                await apply_rls_context(session, user_id=push.user_id)
                push.status = "processing"
                transcript_result = await session.execute(
                    select(Transcript).where(Transcript.push_id == push.id)
                )
                transcript = transcript_result.scalar_one_or_none()
                if transcript is None:
                    raise ValueError("transcript row missing")
                conversation = await storage.load_transcript(transcript.storage_path)
                result = await summarize_push_service(
                    conversation,
                    llm=llm,
                    prompt_version="summarize_v1",
                )
                summaries = [
                    Summary(
                        push_id=push.id,
                        layer="title",
                        content_json={"text": result.title},
                        content_markdown=result.title.strip() + "\n",
                        model=result.model,
                        prompt_version=result.prompt_version,
                        latency_ms=result.latency_ms,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        cost_usd=result.cost_usd,
                        failure_reason=result.failure_reason,
                    ),
                    Summary(
                        push_id=push.id,
                        layer="summary",
                        content_json={"text": result.summary},
                        content_markdown=result.summary.strip() + "\n",
                        model=result.model,
                        prompt_version=result.prompt_version,
                        latency_ms=result.latency_ms,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        cost_usd=result.cost_usd,
                        failure_reason=result.failure_reason,
                    ),
                    Summary(
                        push_id=push.id,
                        layer="details",
                        content_json=result.details.model_dump(mode="json"),
                        content_markdown=json.dumps(result.details.model_dump(mode="json"), indent=2),
                        model=result.model,
                        prompt_version=result.prompt_version,
                        latency_ms=result.latency_ms,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        cost_usd=result.cost_usd,
                        failure_reason=result.failure_reason,
                    ),
                    Summary(
                        push_id=push.id,
                        layer="raw_transcript",
                        content_json={"storage_path": transcript.storage_path},
                        content_markdown=None,
                        model=result.model,
                        prompt_version=result.prompt_version,
                        latency_ms=result.latency_ms,
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        cost_usd=result.cost_usd,
                        failure_reason=result.failure_reason,
                    ),
                ]
                session.add_all(summaries)
                await session.flush()
                redis = ctx.get("redis")
                if redis is not None:
                    try:
                        await redis.enqueue_job(
                            "embed_push_summaries",
                            user_id=str(push.user_id),
                            push_id=str(push.id),
                        )
                    except Exception as exc:
                        # Embedding is best-effort; do not fail completed summarization.
                        logger.warning(
                            "embed enqueue failed after summarization",
                            extra={"push_id": str(push.id), "error": repr(exc)},
                        )
                push.status = "ready"
                session.add(
                    AuditLog(
                        user_id=push.user_id,
                        action="push.completed",
                        resource_type="push",
                        resource_id=push_id,
                        request_id=request_id,
                        metadata_json={"scrub_flags": scrub_flags},
                    )
                )
        return "ready"
    except Exception as exc:
        async with AsyncSession(engine) as session:
            async with session.begin():
                push = await session.get(Push, uuid.UUID(push_id))
                if push is not None:
                    await apply_rls_context(session, user_id=push.user_id)
                    push.status = "failed"
                    push.failure_reason = str(exc)
                    session.add(
                        AuditLog(
                            user_id=push.user_id,
                            action="push.failed",
                            resource_type="push",
                            resource_id=push_id,
                            request_id=request_id,
                            metadata_json={"error": str(exc)},
                        )
                    )
        raise Retry(defer=2) from exc
    finally:
        await engine.dispose()


async def embed_push_summaries(
    ctx: dict[str, Any], *, user_id: str, push_id: str
) -> str:
    """Embed title/summary/details for one push in one transaction (avoids parallel-job deadlocks)."""
    _ = ctx
    engine = make_async_engine(settings.async_database_url)
    embedder = get_embedding_provider(
        mode="live" if (settings.ai_gateway_api_key or settings.voyage_api_key) else "fake"
    )
    layer_order = {"title": 0, "summary": 1, "details": 2}
    try:
        try:
            async with AsyncSession(engine) as session:
                async with session.begin():
                    await apply_rls_context(session, user_id=uuid.UUID(user_id))
                    result = await session.execute(
                        select(Summary).where(
                            Summary.push_id == uuid.UUID(push_id),
                            Summary.layer.in_(["title", "summary", "details"]),
                        )
                    )
                    rows = sorted(
                        result.scalars().all(),
                        key=lambda s: layer_order.get(s.layer, 9),
                    )
                    for summary in rows:
                        await embed_summary_service(
                            summary.id,
                            embedder=embedder,
                            session=session,
                        )
            return "embedded"
        except DBAPIError as exc:
            if isinstance(getattr(exc, "orig", None), DeadlockDetectedError):
                raise Retry(defer=2) from exc
            raise
    finally:
        await engine.dispose()


async def embed_summary(
    ctx: dict[str, Any], *, user_id: str, summary_id: str
) -> str:
    """Legacy per-summary job; prefer embed_push_summaries for new work."""
    _ = ctx
    engine = make_async_engine(settings.async_database_url)
    embedder = get_embedding_provider(
        mode="live" if (settings.ai_gateway_api_key or settings.voyage_api_key) else "fake"
    )
    try:
        try:
            async with AsyncSession(engine) as session:
                async with session.begin():
                    await apply_rls_context(session, user_id=uuid.UUID(user_id))
                    await embed_summary_service(
                        uuid.UUID(summary_id),
                        embedder=embedder,
                        session=session,
                    )
            return "embedded"
        except DBAPIError as exc:
            if isinstance(getattr(exc, "orig", None), DeadlockDetectedError):
                raise Retry(defer=2) from exc
            raise
    finally:
        await engine.dispose()


# Retention jobs run as the service role; RLS context is intentionally not
# applied (the impls issue RLS-bypassing queries). user_id on the AuditLog row
# is None to mark these as system-level events.
async def purge_soft_deleted_pushes(ctx: dict[str, Any]) -> str:
    _ = ctx
    engine = make_async_engine(settings.async_database_url)
    storage = TranscriptStorageService(bucket=settings.transcript_bucket)
    try:
        async with AsyncSession(engine) as session:
            async with session.begin():
                report = await purge_soft_deleted_pushes_impl(session, storage=storage)
                session.add(
                    AuditLog(
                        user_id=None,
                        action="retention.purge_soft_deleted_pushes",
                        resource_type="retention",
                        metadata_json=report.to_dict(),
                    )
                )
        logger.info(
            "retention.purge_soft_deleted_pushes completed",
            extra={"rows_deleted": report.rows_deleted, "job": report.job},
        )
        return f"purged:{report.rows_deleted}"
    except Exception as exc:
        logger.exception(
            "retention.purge_soft_deleted_pushes failed",
            extra={"error": repr(exc)},
        )
        raise
    finally:
        await engine.dispose()


async def purge_failed_pushes(ctx: dict[str, Any]) -> str:
    _ = ctx
    engine = make_async_engine(settings.async_database_url)
    storage = TranscriptStorageService(bucket=settings.transcript_bucket)
    try:
        async with AsyncSession(engine) as session:
            async with session.begin():
                report = await purge_failed_pushes_impl(session, storage=storage)
                session.add(
                    AuditLog(
                        user_id=None,
                        action="retention.purge_failed_pushes",
                        resource_type="retention",
                        metadata_json=report.to_dict(),
                    )
                )
        logger.info(
            "retention.purge_failed_pushes completed",
            extra={"rows_deleted": report.rows_deleted, "job": report.job},
        )
        return f"purged:{report.rows_deleted}"
    except Exception as exc:
        logger.exception(
            "retention.purge_failed_pushes failed",
            extra={"error": repr(exc)},
        )
        raise
    finally:
        await engine.dispose()


async def purge_audit_log(ctx: dict[str, Any]) -> str:
    _ = ctx
    engine = make_async_engine(settings.async_database_url)
    try:
        async with AsyncSession(engine) as session:
            async with session.begin():
                report = await purge_audit_log_impl(session)
                session.add(
                    AuditLog(
                        user_id=None,
                        action="retention.purge_audit_log",
                        resource_type="retention",
                        metadata_json=report.to_dict(),
                    )
                )
        logger.info(
            "retention.purge_audit_log completed",
            extra={"rows_deleted": report.rows_deleted, "job": report.job},
        )
        return f"purged:{report.rows_deleted}"
    except Exception as exc:
        logger.exception(
            "retention.purge_audit_log failed",
            extra={"error": repr(exc)},
        )
        raise
    finally:
        await engine.dispose()


async def purge_revoked_tokens(ctx: dict[str, Any]) -> str:
    _ = ctx
    engine = make_async_engine(settings.async_database_url)
    try:
        async with AsyncSession(engine) as session:
            async with session.begin():
                report = await purge_revoked_tokens_impl(session)
                session.add(
                    AuditLog(
                        user_id=None,
                        action="retention.purge_revoked_tokens",
                        resource_type="retention",
                        metadata_json=report.to_dict(),
                    )
                )
        logger.info(
            "retention.purge_revoked_tokens completed",
            extra={"rows_deleted": report.rows_deleted, "job": report.job},
        )
        return f"purged:{report.rows_deleted}"
    except Exception as exc:
        logger.exception(
            "retention.purge_revoked_tokens failed",
            extra={"error": repr(exc)},
        )
        raise
    finally:
        await engine.dispose()


async def cascade_delete_user(
    ctx: dict[str, Any],
    *,
    user_id: str,
    request_id: str,
) -> str:
    _ = ctx
    engine = make_async_engine(settings.async_database_url)
    storage = TranscriptStorageService(bucket=settings.transcript_bucket)
    user_uuid = uuid.UUID(user_id)
    try:
        async with AsyncSession(engine) as session:
            async with session.begin():
                report = await cascade_delete_user_impl(
                    session, user_id=user_uuid, storage=storage
                )
                session.add(
                    AuditLog(
                        user_id=None,
                        action="user.deleted",
                        resource_type="user",
                        resource_id=user_id,
                        request_id=request_id,
                        metadata_json=report.to_dict(),
                    )
                )
        logger.info(
            "user.deleted",
            extra={
                "user_id": user_id,
                "request_id": request_id,
                "rows_deleted": report.rows_deleted,
                "rows_by_table": report.rows_by_table,
            },
        )
        return json.dumps(report.to_dict())
    except Exception as exc:
        logger.exception(
            "user.deleted failed",
            extra={"user_id": user_id, "request_id": request_id, "error": repr(exc)},
        )
        raise
    finally:
        await engine.dispose()


async def detect_stuck_pushes(ctx: dict[str, Any]) -> str:
    _ = ctx
    engine = make_async_engine(settings.async_database_url)
    try:
        async with AsyncSession(engine) as session:
            async with session.begin():
                stuck = await detect_stuck_pushes_impl(session)
                count = len(stuck)
                if count > 0:
                    sample = [
                        {
                            "push_id": str(s.push_id),
                            "user_id": str(s.user_id),
                            "workspace_id": str(s.workspace_id),
                            "status": s.status,
                            "minutes_stuck": s.minutes_stuck,
                            "failure_reason": s.failure_reason,
                        }
                        for s in stuck[:50]
                    ]
                    session.add(
                        AuditLog(
                            user_id=None,
                            action="stuck_pushes.detected",
                            resource_type="retention",
                            metadata_json={
                                "count": count,
                                "threshold_minutes": settings.stuck_push_minutes,
                                "detected_at": datetime.now(timezone.utc).isoformat(),
                                "stuck_pushes": sample,
                                "truncated": count > 50,
                            },
                        )
                    )
                    logger.warning(
                        "stuck_pushes.detected",
                        extra={
                            "count": count,
                            "threshold_minutes": settings.stuck_push_minutes,
                        },
                    )
        return f"stuck:{count}"
    except Exception as exc:
        logger.exception(
            "stuck_pushes.detect failed",
            extra={"error": repr(exc)},
        )
        raise
    finally:
        await engine.dispose()


async def requeue_push(
    ctx: dict[str, Any],
    *,
    push_id: str,
    request_id: str,
) -> str:
    engine = make_async_engine(settings.async_database_url)
    push_uuid = uuid.UUID(push_id)
    try:
        async with AsyncSession(engine) as session:
            async with session.begin():
                push = await session.get(Push, push_uuid)
                if push is None:
                    return "missing_push"
                if push.status not in ("processing", "failed", "pending"):
                    return f"skipped:{push.status}"
                previous_status = push.status
                push.status = "pending"
                push.failure_reason = None
                session.add(
                    AuditLog(
                        user_id=push.user_id,
                        action="push.requeued",
                        resource_type="push",
                        resource_id=push_id,
                        request_id=request_id,
                        metadata_json={"previous_status": previous_status},
                    )
                )
        redis = ctx.get("redis")
        if redis is not None:
            await redis.enqueue_job(
                "summarize_push",
                push_id=push_id,
                request_id=request_id,
                scrub_flags=[],
            )
        logger.info(
            "push.requeued",
            extra={"push_id": push_id, "request_id": request_id},
        )
        return "pending"
    except Exception as exc:
        logger.exception(
            "push.requeue failed",
            extra={"push_id": push_id, "request_id": request_id, "error": repr(exc)},
        )
        raise
    finally:
        await engine.dispose()


class WorkerSettings:
    functions = [
        summarize_push,
        embed_push_summaries,
        embed_summary,
        purge_soft_deleted_pushes,
        purge_failed_pushes,
        purge_audit_log,
        purge_revoked_tokens,
        cascade_delete_user,
        detect_stuck_pushes,
        requeue_push,
    ]
    cron_jobs = [
        cron(purge_soft_deleted_pushes, hour={3}, minute={0}),
        cron(purge_failed_pushes, hour={3}, minute={15}),
        cron(purge_audit_log, hour={3}, minute={30}),
        cron(purge_revoked_tokens, weekday="sun", hour={4}, minute={0}),
        cron(detect_stuck_pushes, minute={0, 5, 10, 15, 20, 25, 30, 35, 40, 45, 50, 55}),
    ]
    max_tries = 3

