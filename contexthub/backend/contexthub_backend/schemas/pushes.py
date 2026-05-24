"""Pydantic request/response schemas for push endpoints."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class PinnedPushRow(BaseModel):
    """Minimal push row returned by pin endpoints + pinned-list endpoint.

    Full PushRow lands when the push CRUD API ships in Module 8;
    this is the projection the pin feature actually needs.
    """

    id: str
    workspace_id: str
    title: str | None
    commit_message: str | None
    status: str
    pinned_at: datetime | None
    created_at: datetime

    model_config = {"from_attributes": True}
