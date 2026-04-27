from __future__ import annotations

from pydantic import BaseModel


class PushAccepted(BaseModel):
    push_id: str
    status: str
    request_id: str
    scrub_flags: list[str] = []

