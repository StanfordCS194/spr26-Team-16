from __future__ import annotations

import time
from typing import Literal

import httpx

from contexthub_backend.providers.base import EmbeddingProvider, EmbeddingResponse


class VoyageEmbeddingProvider(EmbeddingProvider):
    def __init__(self, *, api_key: str, model: str) -> None:
        self._api_key = api_key
        self._model = model

    async def embed(
        self,
        texts: list[str],
        *,
        input_type: Literal["document", "query"] = "document",
    ) -> EmbeddingResponse:
        started = time.perf_counter()
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                "https://api.voyageai.com/v1/embeddings",
                headers={"Authorization": f"Bearer {self._api_key}"},
                json={"input": texts, "model": self._model, "input_type": input_type},
            )
            response.raise_for_status()
            payload = response.json()
        elapsed_ms = int((time.perf_counter() - started) * 1000)
        usage_tokens = int(payload.get("usage", {}).get("total_tokens", 0))
        vectors = [item["embedding"] for item in payload.get("data", [])]
        return EmbeddingResponse(
            vectors=vectors,
            model=self._model,
            input_tokens=usage_tokens,
            latency_ms=elapsed_ms,
            cost_usd=0.0,
        )

