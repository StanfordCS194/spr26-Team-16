from __future__ import annotations

import json
import logging
import uuid
from typing import Any

from arq import Retry
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


async def purge_soft_deleted_pushes(ctx: dict[str, Any]) -> str:
    _ = ctx
    return "noop"


async def purge_failed_pushes(ctx: dict[str, Any]) -> str:
    _ = ctx
    return "noop"


async def purge_audit_log(ctx: dict[str, Any]) -> str:
    _ = ctx
    return "noop"


async def purge_revoked_tokens(ctx: dict[str, Any]) -> str:
    _ = ctx
    return "noop"


class WorkerSettings:
    functions = [
        summarize_push,
        embed_push_summaries,
        embed_summary,
        purge_soft_deleted_pushes,
        purge_failed_pushes,
        purge_audit_log,
        purge_revoked_tokens,
    ]
    max_tries = 3

