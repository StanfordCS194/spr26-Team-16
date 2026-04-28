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
    title: str | None
    status: str
    source_platform: str
    source_url: str | None
    created_at: datetime
    updated_at: datetime
    commit_message: str | None
    structured_summary_markdown: str | None
    raw_transcript: str | None


class PushHistoryResponse(BaseModel):
    items: list[PushHistoryItem]

