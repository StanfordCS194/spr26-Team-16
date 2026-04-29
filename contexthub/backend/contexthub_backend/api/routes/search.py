from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.api.errors import ValidationError
from contexthub_backend.auth.dependencies import AuthUser, get_current_user, get_rls_session
from contexthub_backend.config import settings
from contexthub_backend.providers import get_embedding_provider
from contexthub_backend.schemas.search import SearchResponse, SearchResultItem
from contexthub_backend.services.search import hybrid_search

router = APIRouter(tags=["search"])


@router.get("/search", response_model=SearchResponse)
async def search(
    q: Annotated[str, Query(min_length=1, max_length=512)],
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    workspace_id: str | None = None,
    include_transcripts: bool = False,
    limit: Annotated[int, Query(ge=1, le=50)] = 20,
) -> SearchResponse:
    user.require_scope("search")

    try:
        workspace_uuid = uuid.UUID(workspace_id) if workspace_id else None
    except ValueError as exc:
        raise ValidationError("workspace_id must be a valid UUID") from exc
    embedder = get_embedding_provider(
        mode="live" if (settings.ai_gateway_api_key or settings.voyage_api_key) else "fake"
    )
    hits = await hybrid_search(
        session=session,
        embedder=embedder,
        query=q,
        workspace_id=workspace_uuid,
        include_transcripts=include_transcripts,
        limit=limit,
    )
    return SearchResponse(
        query=q,
        limit=limit,
        include_transcripts=include_transcripts,
        items=[
            SearchResultItem(
                push_id=str(hit.push_id),
                workspace_id=str(hit.workspace_id),
                title=hit.title,
                status=hit.status,
                created_at=hit.created_at,
                layer=hit.layer,
                snippet=hit.snippet,
                vector_score=hit.vector_score,
                text_score=hit.text_score,
                score=hit.score,
                message_count=hit.message_count,
                transcript_size_bytes=hit.transcript_size_bytes,
            )
            for hit in hits
        ],
    )
