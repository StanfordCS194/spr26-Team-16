from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field


class ShareCreateRequest(BaseModel):
    recipient_email: Annotated[str, Field(min_length=3, max_length=320)]


class ShareRow(BaseModel):
    id: str
    push_id: str
    owner_email: str
    recipient_email: str
    created_at: datetime


class ShareListResponse(BaseModel):
    items: list[ShareRow]


class SharedWithMeItem(BaseModel):
    share_id: str
    push_id: str
    conversation_title: str | None
    status: str
    source_platform: str
    owner_email: str
    shared_at: datetime
    created_at: datetime
    updated_at: datetime
    title: str | None
    summary: str | None
    details: dict | None


class SharedWithMeResponse(BaseModel):
    items: list[SharedWithMeItem]
