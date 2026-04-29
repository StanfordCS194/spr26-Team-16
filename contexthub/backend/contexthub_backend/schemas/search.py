from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class SearchResultItem(BaseModel):
    push_id: str
    workspace_id: str
    title: str | None
    status: str
    created_at: datetime
    layer: str
    snippet: str
    summary: str
    vector_score: float
    text_score: float
    score: float
    message_count: int | None = None
    transcript_size_bytes: int | None = None


class SearchResponse(BaseModel):
    query: str
    limit: int
    include_transcripts: bool
    items: list[SearchResultItem]
