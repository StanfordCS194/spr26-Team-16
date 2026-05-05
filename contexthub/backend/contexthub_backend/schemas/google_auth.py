"""Pydantic schemas for the Google sign-in endpoint."""

from __future__ import annotations

from typing import Annotated

from pydantic import BaseModel, Field


class GoogleAuthRequest(BaseModel):
    id_token: Annotated[str, Field(min_length=20, max_length=8192)]
    token_name: Annotated[str | None, Field(max_length=100)] = None


class GoogleAuthUser(BaseModel):
    user_id: str
    email: str
    display_name: str | None
    avatar_url: str | None


class GoogleAuthResponse(BaseModel):
    token: str  # raw ch_ API token — returned once
    scopes: list[str]
    workspace_id: str
    user: GoogleAuthUser
