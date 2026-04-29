from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.api.errors import NotFoundError, ValidationError
from contexthub_backend.db.models import Push, Summary, Transcript
from contexthub_backend.providers.base import LLMProvider
from contexthub_backend.services.storage import TranscriptStorageService


@dataclass(slots=True)
class PullSourceItem:
    push_id: uuid.UUID
    workspace_id: uuid.UUID
    title: str | None
    created_at: datetime


@dataclass(slots=True)
class PullPayload:
    payload_markdown: str
    provenance: str
    token_estimate: int
    workspace_ids: list[str]
    sources: list[PullSourceItem]


def _estimate_tokens(text: str) -> int:
    # Low-fidelity heuristic for v0 budgeting.
    return max(1, len(text) // 4)


def _platform_framing(target_platform: str) -> str:
    if target_platform == "claude_ai":
        return (
            "Use the following retrieved context from prior conversations. "
            "Treat it as memory and verify assumptions before acting on it."
        )
    return "Use the following retrieved context."


def _structured_summary_prompt(items: list[tuple[str, str]]) -> str:
    blocks = []
    for idx, (title, markdown) in enumerate(items, start=1):
        blocks.append(
            f"## Structured block {idx}: {title}\n\n{markdown.strip()}\n"
        )
    joined = "\n".join(blocks)
    return (
        "Summarize the following structured blocks into one concise markdown context for reuse in a new chat.\n"
        "Focus on stable decisions, important artifacts, assumptions, constraints, and unresolved questions.\n"
        "Do not include provenance, ids, timestamps, or source metadata.\n"
        "Return markdown only.\n\n"
        f"{joined}"
    )


async def _summarize_structured_blocks(
    *,
    llm: LLMProvider,
    items: list[tuple[str, str]],
) -> str:
    if not items:
        return ""
    response = await llm.complete(
        _structured_summary_prompt(items),
        response_format="text",
        max_tokens=1200,
        temperature=0.1,
    )
    text = response.text.strip()
    if not text:
        # Lightweight fallback if a provider returns empty output.
        bullets = "\n".join(f"- {title}" for title, _ in items)
        return f"## Summary of selected structured blocks\n\n{bullets}\n"
    return f"## Summary of selected structured blocks\n\n{text}\n"


async def build_pull_payload(
    *,
    session: AsyncSession,
    storage: TranscriptStorageService,
    llm: LLMProvider,
    selections: list[tuple[uuid.UUID, bool]],
    target_platform: str,
) -> PullPayload:
    if not selections:
        raise ValidationError("at least one pull selection is required")
    if len(selections) > 20:
        raise ValidationError("too many selections; maximum is 20")

    push_ids = [push_id for push_id, _ in selections]
    include_transcript_by_push = {push_id: include_transcript for push_id, include_transcript in selections}

    pushes = (
        await session.execute(
            select(Push)
            .where(Push.id.in_(push_ids), Push.status == "ready")
            .order_by(Push.created_at.asc())
        )
    ).scalars().all()
    if len(pushes) != len(push_ids):
        raise NotFoundError("one or more pushes are not ready or not visible")

    summaries = (
        await session.execute(
            select(Summary).where(Summary.push_id.in_([push.id for push in pushes]))
        )
    ).scalars().all()
    summaries_by_push: dict[uuid.UUID, dict[str, Summary]] = {}
    for summary in summaries:
        summaries_by_push.setdefault(summary.push_id, {})[summary.layer] = summary

    transcripts = (
        await session.execute(
            select(Transcript).where(Transcript.push_id.in_([push.id for push in pushes]))
        )
    ).scalars().all()
    transcripts_by_push = {row.push_id: row for row in transcripts}

    sections: list[str] = []
    sources: list[PullSourceItem] = []
    structured_items: list[tuple[str, str]] = []
    transcript_sections: list[str] = []
    for push in pushes:
        sources.append(
            PullSourceItem(
                push_id=push.id,
                workspace_id=push.workspace_id,
                title=push.title,
                created_at=push.created_at,
            )
        )

        summary = summaries_by_push.get(push.id, {}).get("structured_block")
        if summary is None:
            raise NotFoundError("structured_block summary missing for pull source")
        structured_items.append((push.title or "Untitled push", summary.content_markdown or ""))

        if include_transcript_by_push.get(push.id, False):
            transcript = transcripts_by_push.get(push.id)
            if transcript is None:
                raise NotFoundError("raw transcript missing for selected transcript source")
            conversation = await storage.load_transcript(transcript.storage_path)
            transcript_sections.append(
                f"### {push.title or 'Untitled push'} ({push.id})\n\n{conversation.model_dump_json(indent=2).strip()}\n"
            )

    sections.append(
        await _summarize_structured_blocks(llm=llm, items=structured_items)
    )

    if transcript_sections:
        sections.append("## Conversation transcript:\n\n" + "\n".join(transcript_sections).strip() + "\n")

    provenance_lines = [
        "Context provenance:",
        *[
            f"- {src.push_id} | ws={src.workspace_id} | {src.created_at.isoformat()}"
            for src in sources
        ],
    ]
    provenance = "\n".join(provenance_lines)
    framing = _platform_framing(target_platform)
    payload_markdown = "\n\n".join([framing, *sections]).strip() + "\n"
    token_estimate = _estimate_tokens(payload_markdown)
    return PullPayload(
        payload_markdown=payload_markdown,
        provenance=provenance,
        token_estimate=token_estimate,
        workspace_ids=[str(src.workspace_id) for src in sources],
        sources=sources,
    )
