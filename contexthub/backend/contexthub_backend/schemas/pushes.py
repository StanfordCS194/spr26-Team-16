from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PushAccepted(BaseModel):
    push_id: str
    status: str
    request_id: str
    scrub_flags: list[str] = []


class PushHistoryItem(BaseModel):
    id: str
    workspace_id: str
    conversation_title: str | None
    status: str
    source_platform: str
    source_url: str | None
    created_at: datetime
    updated_at: datetime
    title: str | None
    summary: str | None
    details: dict | None
    raw_transcript: str | None


class PushHistoryResponse(BaseModel):
    items: list[PushHistoryItem]


class PushDetailSummaryLayer(BaseModel):
    layer: str
    content_markdown: str | None
    content_json: dict
    model: str | None
    prompt_version: str | None
    failure_reason: str | None


class PushDetailResponse(BaseModel):
    id: str
    workspace_id: str
    status: str
    failure_reason: str | None
    source_platform: str
    title: str | None
    created_at: datetime
    updated_at: datetime
    transcript_message_count: int | None
    transcript_size_bytes: int | None
    raw_transcript: str | None
    summaries: list[PushDetailSummaryLayer]

