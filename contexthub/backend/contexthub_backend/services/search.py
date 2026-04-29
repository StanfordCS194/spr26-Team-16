from __future__ import annotations

import uuid
from dataclasses import dataclass

from sqlalchemy import Select, String, and_, case, cast, func, literal, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import ColumnElement

from contexthub_backend.db.models import Push, Summary, SummaryEmbedding, Transcript
from contexthub_backend.providers import EmbeddingProvider


@dataclass(slots=True)
class SearchHit:
    push_id: uuid.UUID
    workspace_id: uuid.UUID
    title: str | None
    status: str
    created_at: object
    layer: str
    snippet: str
    vector_score: float
    text_score: float
    score: float
    message_count: int | None
    transcript_size_bytes: int | None


def _snippet(text: str | None, query: str) -> str:
    source = (text or "").strip()
    if not source:
        return ""
    q = query.strip().lower()
    if not q:
        return source[:220]
    idx = source.lower().find(q)
    if idx == -1:
        return source[:220]
    start = max(0, idx - 70)
    end = min(len(source), idx + len(q) + 120)
    snippet = source[start:end]
    if start > 0:
        snippet = "..." + snippet
    if end < len(source):
        snippet = snippet + "..."
    return snippet


async def hybrid_search(
    *,
    session: AsyncSession,
    embedder: EmbeddingProvider,
    query: str,
    workspace_id: uuid.UUID | None,
    include_transcripts: bool,
    limit: int,
) -> list[SearchHit]:
    query_clean = query.strip()
    if not query_clean:
        return []

    embedding_response = await embedder.embed([query_clean], input_type="query")
    query_vector = embedding_response.vectors[0]

    vector_score_expr: ColumnElement[float] = (
        literal(1.0) - SummaryEmbedding.embedding.cosine_distance(query_vector)
    )
    text_score_expr: ColumnElement[float] = func.ts_rank_cd(
        Summary.content_tsv,
        func.plainto_tsquery("english", query_clean),
    )
    score_expr: ColumnElement[float] = (
        case((SummaryEmbedding.summary_id.is_(None), literal(0.0)), else_=vector_score_expr) * literal(0.65)
        + func.coalesce(text_score_expr, literal(0.0)) * literal(0.35)
    )

    layers = ["commit_message", "structured_block"]
    if include_transcripts:
        layers.append("raw_transcript")

    query_stmt: Select = (
        select(
            Push.id.label("push_id"),
            Push.workspace_id.label("workspace_id"),
            Push.title.label("title"),
            Push.status.label("status"),
            Push.created_at.label("created_at"),
            Summary.layer.label("layer"),
            Summary.content_markdown.label("content_markdown"),
            cast(func.coalesce(vector_score_expr, literal(0.0)), String).label("vector_score"),
            cast(func.coalesce(text_score_expr, literal(0.0)), String).label("text_score"),
            cast(func.coalesce(score_expr, literal(0.0)), String).label("score"),
            Transcript.message_count.label("message_count"),
            Transcript.size_bytes.label("transcript_size_bytes"),
        )
        .join(Summary, Summary.push_id == Push.id)
        .outerjoin(SummaryEmbedding, SummaryEmbedding.summary_id == Summary.id)
        .outerjoin(Transcript, Transcript.push_id == Push.id)
        .where(
            and_(
                Push.status == "ready",
                Summary.layer.in_(layers),
                func.coalesce(text_score_expr, literal(0.0)) > literal(0.0),
            )
        )
        .order_by(score_expr.desc(), Push.created_at.desc())
        .limit(limit)
    )
    if workspace_id is not None:
        query_stmt = query_stmt.where(Push.workspace_id == workspace_id)

    rows = (await session.execute(query_stmt)).all()
    hits: list[SearchHit] = []
    for row in rows:
        hits.append(
            SearchHit(
                push_id=row.push_id,
                workspace_id=row.workspace_id,
                title=row.title,
                status=row.status,
                created_at=row.created_at,
                layer=row.layer,
                snippet=_snippet(row.content_markdown, query_clean),
                vector_score=float(row.vector_score or 0.0),
                text_score=float(row.text_score or 0.0),
                score=float(row.score or 0.0),
                message_count=row.message_count,
                transcript_size_bytes=row.transcript_size_bytes,
            )
        )
    return hits
