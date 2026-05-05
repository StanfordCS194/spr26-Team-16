from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Request, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.api.errors import ValidationError
from contexthub_backend.auth.dependencies import (
    AuthUser,
    get_db_session,
    require_admin_scope,
)
from contexthub_backend.config import settings
from contexthub_backend.jobs.registry import enqueue_job
from contexthub_backend.services.retention import (
    detect_stuck_pushes_impl,
    dry_run_all_impl,
)

router = APIRouter(prefix="/v1/admin", tags=["admin"])


class StuckPushItem(BaseModel):
    push_id: str
    user_id: str
    workspace_id: str
    status: str
    minutes_stuck: int
    failure_reason: str | None = None


class StuckPushesResponse(BaseModel):
    items: list[StuckPushItem]
    count: int
    threshold_minutes: int


class RequeueResponse(BaseModel):
    queued: bool
    push_id: str


class CascadeDeleteRequest(BaseModel):
    confirm: str = Field(..., description="Must equal 'DELETE' to proceed.")


class CascadeDeleteResponse(BaseModel):
    queued: bool
    user_id: str


# Admin endpoints bypass RLS: they operate on the service connection (get_db_session)
# rather than get_rls_session, since the underlying impls already do cross-user
# scans (stuck-push detection, retention dry-run, GDPR cascade).
@router.get("/retention/dry-run")
async def retention_dry_run(
    _user: Annotated[AuthUser, Depends(require_admin_scope)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, dict[str, object]]:
    return await dry_run_all_impl(session)


@router.get("/pushes/stuck", response_model=StuckPushesResponse)
async def list_stuck_pushes(
    _user: Annotated[AuthUser, Depends(require_admin_scope)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> StuckPushesResponse:
    rows = await detect_stuck_pushes_impl(session)
    return StuckPushesResponse(
        items=[
            StuckPushItem(
                push_id=str(r.push_id),
                user_id=str(r.user_id),
                workspace_id=str(r.workspace_id),
                status=r.status,
                minutes_stuck=r.minutes_stuck,
                failure_reason=r.failure_reason,
            )
            for r in rows
        ],
        count=len(rows),
        threshold_minutes=settings.stuck_push_minutes,
    )


@router.post(
    "/pushes/{push_id}/requeue",
    response_model=RequeueResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def requeue_push(
    push_id: uuid.UUID,
    request: Request,
    _user: Annotated[AuthUser, Depends(require_admin_scope)],
) -> RequeueResponse:
    request_id = request.state.request_id
    await enqueue_job("requeue_push", push_id=str(push_id), request_id=request_id)
    return RequeueResponse(queued=True, push_id=str(push_id))


@router.post(
    "/users/{user_id}/delete",
    response_model=CascadeDeleteResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def cascade_delete_user(
    user_id: uuid.UUID,
    body: CascadeDeleteRequest,
    request: Request,
    _user: Annotated[AuthUser, Depends(require_admin_scope)],
) -> CascadeDeleteResponse:
    # Literal-string confirm guards against accidental fire from a misrouted
    # form post or curl typo; this is irreversible (GDPR cascade).
    if body.confirm != "DELETE":
        raise ValidationError("confirm field must be the literal string 'DELETE'")
    request_id = request.state.request_id
    await enqueue_job(
        "cascade_delete_user",
        user_id=str(user_id),
        request_id=request_id,
    )
    return CascadeDeleteResponse(queued=True, user_id=str(user_id))
