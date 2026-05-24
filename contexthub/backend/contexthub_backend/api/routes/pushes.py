"""Push endpoints — pin/unpin/list-pinned.

This is the pin-feature slice; the full push CRUD lands with Module 8.

  POST   /v1/pushes/{push_id}/pin                — pin (idempotent)
  DELETE /v1/pushes/{push_id}/pin                — unpin (idempotent)
  GET    /v1/workspaces/{workspace_id}/pushes/pinned
                                                 — list caller's pinned pushes
                                                   in a workspace, newest pin first
"""

from __future__ import annotations

import uuid
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.api.errors import NotFoundError
from contexthub_backend.auth.dependencies import AuthUser, get_current_user, get_rls_session
from contexthub_backend.db.models import Push
from contexthub_backend.schemas.pushes import PinnedPushRow

router = APIRouter(tags=["pushes"])


@router.post("/pushes/{push_id}/pin", response_model=PinnedPushRow)
async def pin_push(
    push_id: uuid.UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> PinnedPushRow:
    # COALESCE keeps the original pin time when re-pinning (idempotent).
    # RLS filters to the caller's pushes; soft-deleted rows are excluded.
    result = await session.execute(
        text(
            """
            UPDATE pushes
               SET pinned_at = COALESCE(pinned_at, now()),
                   updated_at = now()
             WHERE id = :push_id
               AND deleted_at IS NULL
         RETURNING id, workspace_id, title, commit_message, status, pinned_at, created_at
            """
        ),
        {"push_id": str(push_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise NotFoundError(f"push {push_id} not found")
    return PinnedPushRow(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        title=row["title"],
        commit_message=row["commit_message"],
        status=row["status"],
        pinned_at=row["pinned_at"],
        created_at=row["created_at"],
    )


@router.delete("/pushes/{push_id}/pin", response_model=PinnedPushRow)
async def unpin_push(
    push_id: uuid.UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> PinnedPushRow:
    result = await session.execute(
        text(
            """
            UPDATE pushes
               SET pinned_at = NULL,
                   updated_at = now()
             WHERE id = :push_id
               AND deleted_at IS NULL
         RETURNING id, workspace_id, title, commit_message, status, pinned_at, created_at
            """
        ),
        {"push_id": str(push_id)},
    )
    row = result.mappings().first()
    if row is None:
        raise NotFoundError(f"push {push_id} not found")
    return PinnedPushRow(
        id=str(row["id"]),
        workspace_id=str(row["workspace_id"]),
        title=row["title"],
        commit_message=row["commit_message"],
        status=row["status"],
        pinned_at=row["pinned_at"],
        created_at=row["created_at"],
    )


@router.get(
    "/workspaces/{workspace_id}/pushes/pinned",
    response_model=list[PinnedPushRow],
)
async def list_pinned_pushes(
    workspace_id: uuid.UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> list[PinnedPushRow]:
    result = await session.execute(
        select(Push)
        .where(
            Push.workspace_id == workspace_id,
            Push.pinned_at.is_not(None),
            Push.deleted_at.is_(None),
        )
        .order_by(Push.pinned_at.desc())
    )
    rows = result.scalars().all()
    return [
        PinnedPushRow(
            id=str(r.id),
            workspace_id=str(r.workspace_id),
            title=r.title,
            commit_message=r.commit_message,
            status=r.status,
            pinned_at=r.pinned_at,
            created_at=r.created_at,
        )
        for r in rows
    ]
