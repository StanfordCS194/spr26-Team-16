from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Query, Request, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_interchange.models import ConversationV0

from contexthub_backend.api.errors import NotFoundError, ValidationError
from contexthub_backend.auth.dependencies import AuthUser, get_current_user, get_rls_session
from contexthub_backend.config import settings
from contexthub_backend.db.models import (
    AuditLog,
    InterchangeFormatVersion,
    Push,
    Summary,
    Transcript,
    Workspace,
)
from contexthub_backend.ingress.rate_limit import RateLimiter
from contexthub_backend.ingress.scrub import scrub_sensitive_patterns
from contexthub_backend.jobs.registry import enqueue_job
from contexthub_backend.schemas.pushes import PushAccepted, PushHistoryItem, PushHistoryResponse
from contexthub_backend.schemas.pushes import PushDetailResponse, PushDetailSummaryLayer
from contexthub_backend.services.storage import TranscriptStorageService

logger = logging.getLogger(__name__)
router = APIRouter(tags=["pushes"])
rate_limiter = RateLimiter(per_minute=settings.rate_limit_per_minute)
storage = TranscriptStorageService(bucket=settings.transcript_bucket)


def _idempotency_key(conversation: ConversationV0, incoming_key: str | None) -> str:
    if incoming_key:
        return incoming_key
    payload = json.dumps(conversation.model_dump(mode="json"), sort_keys=True).encode()
    return hashlib.sha256(payload).hexdigest()


def _summary_text(summary: Summary | None) -> str | None:
    if summary is None:
        return None
    text = summary.content_json.get("text")
    if isinstance(text, str) and text.strip():
        return text.strip()
    if summary.content_markdown and summary.content_markdown.strip():
        return summary.content_markdown.strip()
    return None


def _canonical_layer(layer: str) -> str:
    if layer == "commit_message":
        return "title"
    if layer == "structured_block":
        return "summary"
    return layer


@router.post(
    "/workspaces/{workspace_id}/pushes",
    response_model=PushAccepted,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_push(
    workspace_id: uuid.UUID,
    conversation: ConversationV0,
    request: Request,
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    idempotency_header: str | None = Header(default=None, alias="Idempotency-Key"),
) -> PushAccepted:
    user.require_scope("push")
    await rate_limiter.check(user_id=str(user.user_id), bucket="push", window_seconds=60)
    workspace_result = await session.execute(select(Workspace).where(Workspace.id == workspace_id))
    workspace = workspace_result.scalar_one_or_none()
    if workspace is None:
        raise NotFoundError("workspace not found")
    version_result = await session.execute(
        select(InterchangeFormatVersion.version).where(
            InterchangeFormatVersion.version == conversation.spec_version
        )
    )
    if version_result.scalar_one_or_none() is None:
        raise ValidationError(f"unsupported spec_version: {conversation.spec_version}")

    scrub_result = scrub_sensitive_patterns(conversation)
    idempotency_key = _idempotency_key(conversation, idempotency_header)
    request_id = request.state.request_id

    try:
        async with session.begin_nested():
            push = Push(
                workspace_id=workspace_id,
                user_id=user.user_id,
                source_platform=conversation.source.platform,
                source_url=str(conversation.source.url) if conversation.source.url else None,
                source_conversation_id=conversation.source.conversation_id,
                interchange_version=conversation.spec_version,
                title=conversation.metadata.title if conversation.metadata else None,
                status="pending",
                idempotency_key=idempotency_key,
            )
            session.add(push)
            await session.flush()
            stored = await storage.store_transcript(
                workspace_id=str(workspace_id),
                push_id=str(push.id),
                conversation=conversation,
            )
            session.add(
                Transcript(
                    push_id=push.id,
                    storage_path=stored.storage_path,
                    sha256=stored.sha256,
                    size_bytes=stored.size_bytes,
                    message_count=stored.message_count,
                )
            )
            session.add(
                AuditLog(
                    user_id=user.user_id,
                    action="push.create",
                    resource_type="push",
                    resource_id=str(push.id),
                    request_id=request_id,
                    metadata_json={"scrub_flags": scrub_result.findings},
                )
            )
            await enqueue_job(
                "summarize_push",
                push_id=str(push.id),
                request_id=request_id,
                scrub_flags=scrub_result.findings,
            )
        return PushAccepted(
            push_id=str(push.id),
            status=push.status,
            request_id=request_id,
            scrub_flags=scrub_result.findings,
        )
    except IntegrityError as exc:
        # Only idempotency-key uniqueness conflicts should map to reuse behavior.
        msg = str(exc).lower()
        if "idempotency" not in msg:
            raise
        existing = await session.execute(
            select(Push).where(
                Push.user_id == user.user_id,
                Push.idempotency_key == idempotency_key,
            )
        )
        prior = existing.scalar_one_or_none()
        if prior is None:
            raise
        logger.info(
            "idempotent push reuse",
            extra={"request_id": request_id, "user_id": str(user.user_id), "push_id": str(prior.id)},
        )
        return PushAccepted(
            push_id=str(prior.id),
            status=prior.status,
            request_id=request_id,
            scrub_flags=[],
        )


@router.get("/pushes/history", response_model=PushHistoryResponse)
async def get_push_history(
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
) -> PushHistoryResponse:
    """Return recent pushes for the authenticated user with summaries and transcript."""
    user.require_scope("read")

    pushes_result = await session.execute(
        select(Push)
        .where(Push.user_id == user.user_id)
        .order_by(Push.created_at.desc())
        .limit(limit)
    )
    pushes = pushes_result.scalars().all()
    if not pushes:
        return PushHistoryResponse(items=[])

    push_ids = [push.id for push in pushes]

    summaries_result = await session.execute(
        select(Summary).where(Summary.push_id.in_(push_ids))
    )
    summaries_by_push: dict[uuid.UUID, dict[str, Summary]] = {}
    for summary in summaries_result.scalars().all():
        canonical = _canonical_layer(summary.layer)
        summaries_by_push.setdefault(summary.push_id, {})[canonical] = summary

    transcript_result = await session.execute(
        select(Transcript).where(Transcript.push_id.in_(push_ids))
    )
    transcripts_by_push = {row.push_id: row for row in transcript_result.scalars().all()}

    items: list[PushHistoryItem] = []
    for push in pushes:
        summary_layers = summaries_by_push.get(push.id, {})
        transcript = transcripts_by_push.get(push.id)
        raw_transcript: str | None = None
        if transcript is not None:
            try:
                conversation = await storage.load_transcript(transcript.storage_path)
                raw_transcript = json.dumps(conversation.model_dump(mode="json"), indent=2)
            except Exception:
                # If storage is unavailable, still return push metadata/summaries.
                raw_transcript = None

        items.append(
            PushHistoryItem(
                id=str(push.id),
                workspace_id=str(push.workspace_id),
                conversation_title=push.title,
                status=push.status,
                source_platform=push.source_platform,
                source_url=push.source_url,
                created_at=push.created_at,
                updated_at=push.updated_at,
                title=_summary_text(summary_layers.get("title")),
                summary=_summary_text(summary_layers.get("summary")),
                details=summary_layers.get("details").content_json
                if summary_layers.get("details")
                else None,
                raw_transcript=raw_transcript,
            )
        )

    return PushHistoryResponse(items=items)


@router.get("/pushes/{push_id}", response_model=PushDetailResponse)
async def get_push(
    push_id: uuid.UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> PushDetailResponse:
    user.require_scope("read")

    push_result = await session.execute(select(Push).where(Push.id == push_id))
    push = push_result.scalar_one_or_none()
    if push is None:
        raise NotFoundError("push not found")

    summaries_result = await session.execute(select(Summary).where(Summary.push_id == push.id))
    summaries = summaries_result.scalars().all()

    transcript_result = await session.execute(
        select(Transcript).where(Transcript.push_id == push.id)
    )
    transcript = transcript_result.scalar_one_or_none()
    raw_transcript: str | None = None
    if transcript is not None:
        try:
            conversation = await storage.load_transcript(transcript.storage_path)
            raw_transcript = json.dumps(conversation.model_dump(mode="json"), indent=2)
        except Exception:
            raw_transcript = None

    return PushDetailResponse(
        id=str(push.id),
        workspace_id=str(push.workspace_id),
        status=push.status,
        failure_reason=push.failure_reason,
        source_platform=str(push.source_platform),
        title=push.title,
        created_at=push.created_at,
        updated_at=push.updated_at,
        transcript_message_count=transcript.message_count if transcript else None,
        transcript_size_bytes=transcript.size_bytes if transcript else None,
        raw_transcript=raw_transcript,
        summaries=[
            PushDetailSummaryLayer(
                layer=_canonical_layer(summary.layer),
                content_markdown=summary.content_markdown,
                content_json=summary.content_json,
                model=summary.model,
                prompt_version=summary.prompt_version,
                failure_reason=summary.failure_reason,
            )
            for summary in summaries
        ],
    )

