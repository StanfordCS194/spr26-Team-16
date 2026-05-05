"""Pydantic schemas for POST /v1/me/bootstrap."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, EmailStr, Field


class MeBootstrapRequest(BaseModel):
    # Optional metadata mirrored from Supabase user_metadata. The endpoint
    # works without these — they only enrich the profile row if present.
    email: EmailStr | None = None
    display_name: Annotated[str | None, Field(max_length=200)] = None
    avatar_url: Annotated[str | None, Field(max_length=2000)] = None


class MeBootstrapUser(BaseModel):
    user_id: str
    email: str | None
    display_name: str | None
    avatar_url: str | None


class MeBootstrapResponse(BaseModel):
    user: MeBootstrapUser
    workspace_id: str
