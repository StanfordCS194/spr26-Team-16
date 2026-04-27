from __future__ import annotations

import hashlib
import json
import logging
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Header, Request, status
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
    Transcript,
    Workspace,
)
from contexthub_backend.ingress.rate_limit import RateLimiter
from contexthub_backend.ingress.scrub import scrub_sensitive_patterns
from contexthub_backend.jobs.registry import enqueue_job
from contexthub_backend.schemas.pushes import PushAccepted
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

