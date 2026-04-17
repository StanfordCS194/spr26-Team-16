## Decisions

- **Emit full artifact bodies in structured block** — Artifacts are authoritative; don't truncate on push

## Artifacts

### search_router (code)
```python
from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Sequence

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, text

from contexthub.models import Push, Summary, SummaryEmbedding
from contexthub.providers import EmbeddingProvider

log = logging.getLogger(__name__)


@dataclass(slots=True)
class SearchResult:
    push_id: str
    commit_message: str
    score: float
    workspace_id: str


class SearchRouter:
    def __init__(self, session: AsyncSession, embedder: EmbeddingProvider):
        self._session = session
        self._embedder = embedder

    async def hybrid(self, query: str, workspace_id: str, limit: int = 20) -> Sequence[SearchResult]:
        vector = await self._embedder.embed(query)
        vector_hits = await self._vector_lookup(vector, workspace_id, limit)
        bm25_hits = await self._bm25_lookup(query, workspace_id, limit)
        merged = self._reciprocal_rank_fusion(vector_hits, bm25_hits)
        return merged[:limit]

    async def _vector_lookup(self, vector, workspace_id, limit):
        stmt = (
            select(
                Push.id.label('push_id'),
                Push.commit_message,
                Push.workspace_id,
                (1 - SummaryEmbedding.embedding.cosine_distance(vector)).label('score'),
            )
            .join(Summary, Summary.push_id == Push.id)
            .join(SummaryEmbedding, SummaryEmbedding.summary_id == Summary.id)
            .where(Push.workspace_id == workspace_id, Push.deleted_at.is_(None))
            .order_by(SummaryEmbedding.embedding.cosine_distance(vector))
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [SearchResult(str(r.push_id), r.commit_message, float(r.score), str(r.workspace_id)) for r in rows]

    async def _bm25_lookup(self, query, workspace_id, limit):
        ts_query = func.websearch_to_tsquery('english', query)
        stmt = (
            select(
                Push.id.label('push_id'),
                Push.commit_message,
                Push.workspace_id,
                func.ts_rank(Summary.content_tsv, ts_query).label('score'),
            )
            .join(Summary, Summary.push_id == Push.id)
            .where(
                Push.workspace_id == workspace_id,
                Push.deleted_at.is_(None),
                Summary.content_tsv.op('@@')(ts_query),
            )
            .order_by(text('score DESC'))
            .limit(limit)
        )
        rows = (await self._session.execute(stmt)).all()
        return [SearchResult(str(r.push_id), r.commit_message, float(r.score), str(r.workspace_id)) for r in rows]

    @staticmethod
    def _reciprocal_rank_fusion(a, b, k=60):
        scores: dict[str, SearchResult] = {}
        for rank, hit in enumerate(a):
            scores[hit.push_id] = SearchResult(hit.push_id, hit.commit_message, 1 / (k + rank + 1), hit.workspace_id)
        for rank, hit in enumerate(b):
            if hit.push_id in scores:
                existing = scores[hit.push_id]
                scores[hit.push_id] = SearchResult(hit.push_id, hit.commit_message, existing.score + 1 / (k + rank + 1), hit.workspace_id)
            else:
                scores[hit.push_id] = SearchResult(hit.push_id, hit.commit_message, 1 / (k + rank + 1), hit.workspace_id)
        return sorted(scores.values(), key=lambda r: r.score, reverse=True)
```
