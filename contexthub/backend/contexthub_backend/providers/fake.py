from __future__ import annotations

import json
import time
from typing import Literal

from .base import EmbeddingProvider, EmbeddingResponse, LLMProvider, LLMResponse


class FakeLLMProvider(LLMProvider):
    async def complete(
        self,
        prompt: str,
        *,
        response_format: Literal["json", "text"] = "json",
        max_tokens: int = 1600,
        temperature: float = 0.0,
    ) -> LLMResponse:
        _ = (max_tokens, temperature)
        started = time.perf_counter()
        summary_text = prompt[:80] or "Conversation captured"
        details = {
            "summary": "Captured conversation context for downstream reuse.",
            "key_takeaways": [
                "Captured durable conversation context.",
                "Stored a snippet for later search and retrieval.",
                "Next work should clarify what to implement next.",
            ],
            "tags": ["captured", "context", "snippet", "follow-up"],
        }
        text_payload = json.dumps(
            {
                "title": f"Summary: {summary_text}",
                "details": details,
                "raw_transcript": "Raw transcript is stored separately.",
            }
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response_format == "text":
            text_payload = details["summary"]
        return LLMResponse(
            text=text_payload,
            model="fake-llm",
            prompt_version="summarize_v1",
            input_tokens=50,
            output_tokens=80,
            latency_ms=latency_ms,
            cost_usd=0.0,
        )


class FakeEmbeddingProvider(EmbeddingProvider):
    async def embed(
        self,
        texts: list[str],
        *,
        input_type: Literal["document", "query"] = "document",
    ) -> EmbeddingResponse:
        _ = input_type
        vectors: list[list[float]] = []
        for text in texts:
            base = float(len(text) % 17)
            vectors.append([base + float(i % 7) for i in range(1024)])
        return EmbeddingResponse(
            vectors=vectors,
            model="fake-embedding",
            input_tokens=max(1, sum(len(text) for text in texts) // 4),
            latency_ms=1,
            cost_usd=0.0,
        )

