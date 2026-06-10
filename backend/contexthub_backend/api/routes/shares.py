"""Share endpoints: grant another user read access to a push's summary.

A share gives the recipient read access to the push row and its summary
layers (title/summary/details) — never the raw transcript. Access is
enforced by the RLS policies added in migration 006; these routes only add
the ownership checks RLS can't express per-endpoint (e.g. "only the owner
may create or revoke shares") and the auth.users email lookups, which go
through SECURITY DEFINER SQL helpers.
"""

from __future__ import annotations

import re
import uuid
from typing import Annotated

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.api.errors import ForbiddenError, NotFoundError, ValidationError
from contexthub_backend.api.routes.pushes import _canonical_layer, _summary_text
from contexthub_backend.auth.dependencies import AuthUser, get_current_user, get_rls_session
from contexthub_backend.db.models import AuditLog, Push, PushShare, Summary
from contexthub_backend.schemas.shares import (
    ShareCreateRequest,
    ShareListResponse,
    ShareRow,
    SharedWithMeItem,
    SharedWithMeResponse,
)

router = APIRouter(tags=["shares"])

_EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _share_row(share: PushShare) -> ShareRow:
    return ShareRow(
        id=str(share.id),
        push_id=str(share.push_id),
        owner_email=share.owner_email,
        recipient_email=share.recipient_email,
        created_at=share.created_at,
    )


async def _get_push_or_404(session: AsyncSession, push_id: uuid.UUID) -> Push:
    result = await session.execute(
        select(Push).where(Push.id == push_id, Push.deleted_at.is_(None))
    )
    push = result.scalar_one_or_none()
    if push is None:
        raise NotFoundError("push not found")
    return push


@router.post(
    "/pushes/{push_id}/shares",
    response_model=ShareRow,
    status_code=status.HTTP_201_CREATED,
)
async def create_share(
    push_id: uuid.UUID,
    body: ShareCreateRequest,
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> ShareRow:
    user.require_scope("push")

    push = await _get_push_or_404(session, push_id)
    if push.user_id != user.user_id:
        raise ForbiddenError("only the owner can share a push")

    email = body.recipient_email.strip().lower()
    if not _EMAIL_RE.match(email):
        raise ValidationError("invalid email address")

    recipient_id = (
        await session.execute(
            text("SELECT public.ch_user_id_by_email(:email)"), {"email": email}
        )
    ).scalar_one_or_none()
    if recipient_id is None:
        raise NotFoundError("no ContextHub user with that email")
    if recipient_id == user.user_id:
        raise ValidationError("you cannot share a push with yourself")

    existing = (
        await session.execute(
            select(PushShare).where(
                PushShare.push_id == push.id,
                PushShare.recipient_user_id == recipient_id,
            )
        )
    ).scalar_one_or_none()
    if existing is not None:
        raise ValidationError("this push is already shared with that user")

    owner_email = (
        await session.execute(
            text("SELECT public.ch_user_email_by_id(:uid)"), {"uid": str(user.user_id)}
        )
    ).scalar_one_or_none() or ""

    share = PushShare(
        push_id=push.id,
        owner_user_id=user.user_id,
        recipient_user_id=recipient_id,
        owner_email=owner_email,
        recipient_email=email,
    )
    session.add(share)
    session.add(
        AuditLog(
            user_id=user.user_id,
            action="share.create",
            resource_type="push",
            resource_id=str(push.id),
            metadata_json={"recipient_email": email},
        )
    )
    await session.flush()
    # created_at is a server default; load it explicitly (async sessions
    # cannot lazy-load expired attributes).
    await session.refresh(share)
    return _share_row(share)


@router.get("/pushes/{push_id}/shares", response_model=ShareListResponse)
async def list_shares(
    push_id: uuid.UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> ShareListResponse:
    """List who a push is shared with. RLS scopes the result: the owner sees
    every share, a recipient sees only their own."""
    user.require_scope("read")

    await _get_push_or_404(session, push_id)
    shares = (
        (
            await session.execute(
                select(PushShare)
                .where(PushShare.push_id == push_id)
                .order_by(PushShare.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return ShareListResponse(items=[_share_row(share) for share in shares])


@router.delete("/pushes/{push_id}/shares/{share_id}", status_code=status.HTTP_204_NO_CONTENT)
async def revoke_share(
    push_id: uuid.UUID,
    share_id: uuid.UUID,
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
) -> None:
    """Revoke a share. The owner revokes access; a recipient removes the
    share from their own dashboard."""
    user.require_scope("push")

    share = (
        await session.execute(
            select(PushShare).where(PushShare.id == share_id, PushShare.push_id == push_id)
        )
    ).scalar_one_or_none()
    if share is None:
        raise NotFoundError("share not found")

    is_owner = share.owner_user_id == user.user_id
    await session.delete(share)
    session.add(
        AuditLog(
            user_id=user.user_id,
            action="share.revoke" if is_owner else "share.leave",
            resource_type="push",
            resource_id=str(push_id),
            metadata_json={"recipient_email": share.recipient_email},
        )
    )
    await session.flush()
    return None


@router.get("/shares/received", response_model=SharedWithMeResponse)
async def shares_received(
    user: Annotated[AuthUser, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_rls_session)],
    limit: Annotated[int, Query(ge=1, le=50)] = 25,
) -> SharedWithMeResponse:
    """Pushes other users have shared with the caller, newest share first."""
    user.require_scope("read")

    rows = (
        await session.execute(
            select(PushShare, Push)
            .join(Push, Push.id == PushShare.push_id)
            .where(
                PushShare.recipient_user_id == user.user_id,
                Push.deleted_at.is_(None),
            )
            .order_by(PushShare.created_at.desc())
            .limit(limit)
        )
    ).all()
    if not rows:
        return SharedWithMeResponse(items=[])

    push_ids = [push.id for _, push in rows]
    summaries_result = await session.execute(
        select(Summary).where(Summary.push_id.in_(push_ids))
    )
    summaries_by_push: dict[uuid.UUID, dict[str, Summary]] = {}
    for summary in summaries_result.scalars().all():
        canonical = _canonical_layer(summary.layer)
        summaries_by_push.setdefault(summary.push_id, {})[canonical] = summary

    items: list[SharedWithMeItem] = []
    for share, push in rows:
        summary_layers = summaries_by_push.get(push.id, {})
        items.append(
            SharedWithMeItem(
                share_id=str(share.id),
                push_id=str(push.id),
                conversation_title=push.title,
                status=push.status,
                source_platform=str(push.source_platform),
                owner_email=share.owner_email,
                shared_at=share.created_at,
                created_at=push.created_at,
                updated_at=push.updated_at,
                title=_summary_text(summary_layers.get("title")),
                summary=_summary_text(summary_layers.get("summary")),
                details=summary_layers.get("details").content_json
                if summary_layers.get("details")
                else None,
            )
        )
    return SharedWithMeResponse(items=items)
