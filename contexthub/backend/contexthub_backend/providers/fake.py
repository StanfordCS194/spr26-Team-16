from __future__ import annotations

import time
from typing import Literal

from contexthub_interchange.models import (
    Artifact,
    Decision,
    OpenQuestion,
    StructuredBlockV0,
)

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
        block = StructuredBlockV0(
            spec_version="ch.v0.1",
            decisions=[Decision(title="Captured", rationale="Stored by fake provider")],
            artifacts=[Artifact(kind="other", name="Snippet", body=summary_text)],
            open_questions=[OpenQuestion(question="What should be implemented next?")],
            assumptions=[],
            constraints=[],
        )
        text_payload = (
            '{"commit_message":"Summary: %s","structured_block":%s,"raw_transcript":"Raw transcript is stored separately."}'
            % (summary_text, block.model_dump_json())
        )
        latency_ms = int((time.perf_counter() - started) * 1000)
        if response_format == "text":
            text_payload = f"Summary: {summary_text}"
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
            vectors.append([base, base + 1.0, base + 2.0])
        return EmbeddingResponse(
            vectors=vectors,
            model="fake-embedding",
            input_tokens=max(1, sum(len(text) for text in texts) // 4),
            latency_ms=1,
            cost_usd=0.0,
        )

