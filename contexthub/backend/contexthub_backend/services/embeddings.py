from __future__ import annotations

import uuid

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from contexthub_backend.providers.base import EmbeddingProvider
from contexthub_backend.db.models import Summary, SummaryEmbedding


async def embed_summary(
    summary_id: uuid.UUID,
    *,
    embedder: EmbeddingProvider,
    session: AsyncSession,
) -> None:
    result = await session.execute(select(Summary).where(Summary.id == summary_id))
    summary = result.scalar_one_or_none()
    if summary is None or not summary.content_markdown:
        return
    response = await embedder.embed([summary.content_markdown], input_type="document")
    vector = response.vectors[0] if response.vectors else None
    if vector is None:
        return
    existing = await session.get(SummaryEmbedding, summary_id)
    if existing:
        existing.embedding = vector
        existing.embedding_model = response.model
    else:
        session.add(
            SummaryEmbedding(
                summary_id=summary_id,
                embedding=vector,
                embedding_model=response.model,
            )
        )
    await session.flush()

