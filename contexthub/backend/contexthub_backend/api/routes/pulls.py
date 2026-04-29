from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.auth.dependencies import AuthUser, get_current_user, get_rls_session
from contexthub_backend.config import settings
from contexthub_backend.db.models import AuditLog, Pull
from contexthub_backend.providers import get_llm_provider
from contexthub_backend.schemas.pulls import PullRequest, PullResponse, PullSource
from contexthub_backend.services.context_builder import build_pull_payload
from contexthub_backend.services.egress import sanitize_egress_markdown
from contexthub_backend.services.storage import TranscriptStorageService

router = APIRouter(tags=["pulls"])
storage = TranscriptStorageService(bucket=settings.transcript_bucket)


@router.post("/pulls", response_model=PullResponse)
async def create_pull(
    body: PullRequest,
    request: Request,
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> PullResponse:
    user.require_scope("pull")
    selections = [
        (uuid.UUID(selection.push_id), selection.include_transcript)
        for selection in body.selections
    ]
    push_ids = [push_id for push_id, _ in selections]
    llm = get_llm_provider(
        mode="live" if (settings.ai_gateway_api_key or settings.anthropic_api_key) else "fake"
    )

    payload = await build_pull_payload(
        session=session,
        storage=storage,
        llm=llm,
        selections=selections,
        target_platform=body.target_platform,
    )
    payload_markdown = sanitize_egress_markdown(payload.payload_markdown)

    pull_row = Pull(
        user_id=user.user_id,
        target_platform=body.target_platform,
        origin=body.origin,
        resolution="summary",
        push_ids=[str(push_id) for push_id in push_ids],
        workspace_ids=payload.workspace_ids,
        token_estimate=payload.token_estimate,
    )
    session.add(pull_row)
    await session.flush()
    session.add(
        AuditLog(
            user_id=user.user_id,
            action="pull.create",
            resource_type="pull",
            resource_id=str(pull_row.id),
            request_id=request.state.request_id,
            metadata_json={
                "mode": "summary_plus_optional_transcripts",
                "target_platform": body.target_platform,
                "source_push_ids": [str(push_id) for push_id in push_ids],
                "transcript_push_ids": [
                    str(push_id)
                    for push_id, include_transcript in selections
                    if include_transcript
                ],
            },
        )
    )

    return PullResponse(
        mode="summary_plus_optional_transcripts",
        target_platform=body.target_platform,
        token_estimate=payload.token_estimate,
        payload_markdown=payload_markdown,
        provenance=payload.provenance,
        sources=[
            PullSource(
                push_id=str(source.push_id),
                workspace_id=str(source.workspace_id),
                title=source.title,
                created_at=source.created_at,
            )
            for source in payload.sources
        ],
    )
