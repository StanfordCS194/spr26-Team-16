"""Pydantic request/response schemas for auth endpoints."""

from __future__ import annotations

from datetime import datetime
import uuid
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


class DevLoginRequest(BaseModel):
    user_id: uuid.UUID | None = None


class DevLoginResponse(BaseModel):
    token: str
    user_id: str
    expires_at: datetime


class ExtensionPairingCreateRequest(BaseModel):
    token_name: Annotated[str, Field(min_length=1, max_length=100)] = "chrome-extension"
    scopes: list[str] = ["push", "pull", "search", "read"]
    workspace_id: uuid.UUID | None = None
    api_base_url: str | None = None
    ttl_seconds: Annotated[int | None, Field(ge=60, le=1800)] = None

    @field_validator("scopes")
    @classmethod
    def validate_scopes(cls, v: list[str]) -> list[str]:
        invalid = set(v) - VALID_SCOPES
        if invalid:
            raise ValueError(f"invalid scopes: {sorted(invalid)}")
        if not v:
            raise ValueError("scopes must not be empty")
        return v


class ExtensionPairingCreateResponse(BaseModel):
    code: str
    expires_at: datetime


class ExtensionPairingExchangeRequest(BaseModel):
    code: Annotated[str, Field(min_length=4, max_length=128)]


class ExtensionPairingExchangeResponse(BaseModel):
    token: str
    scopes: list[str]
    workspace_id: str | None
    api_base_url: str | None
    expires_at: datetime
