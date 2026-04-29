from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class PullSelection(BaseModel):
    push_id: str
    include_transcript: bool = False


class PullRequest(BaseModel):
    selections: list[PullSelection] = Field(min_length=1, max_length=20)
    target_platform: str = Field(pattern="^(claude_ai)$")
    origin: str = Field(default="dashboard", pattern="^(dashboard|extension)$")


class PullSource(BaseModel):
    push_id: str
    workspace_id: str
    title: str | None
    created_at: datetime


class PullResponse(BaseModel):
    mode: str = "summary_plus_optional_transcripts"
    target_platform: str
    token_estimate: int
    payload_markdown: str
    provenance: str
    sources: list[PullSource]
