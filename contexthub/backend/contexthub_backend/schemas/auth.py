"""Pydantic request/response schemas for auth endpoints."""

from __future__ import annotations

from datetime import datetime
from typing import Annotated

from pydantic import BaseModel, Field, field_validator

from contexthub_backend.auth.tokens import VALID_SCOPES


class TokenCreateRequest(BaseModel):
    name: Annotated[str, Field(min_length=1, max_length=100)]
    scopes: list[str] = ["push", "pull", "search", "read"]

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: list[str]) -> list[str]:
        invalid = set(v) - VALID_SCOPES
        if invalid:
            raise ValueError(f"invalid scopes: {sorted(invalid)}")
        if not v:
            raise ValueError("scopes must not be empty")
        return v


class TokenRow(BaseModel):
    id: str
    name: str
    scopes: list[str]
    created_at: datetime
    last_used_at: datetime | None
    revoked_at: datetime | None

    model_config = {"from_attributes": True}


class TokenMintResponse(TokenRow):
    token: str  # raw token — returned once only, never stored


class MeResponse(BaseModel):
    user_id: str
    display_name: str | None
    avatar_url: str | None
