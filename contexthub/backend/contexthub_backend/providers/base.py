from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from typing import Protocol

@dataclass(slots=True)
class LLMResponse:
    text: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float
    failure_reason: str | None = None


@dataclass(slots=True)
class EmbeddingResponse:
    vectors: list[list[float]]
    model: str
    input_tokens: int
    latency_ms: int
    cost_usd: float


class LLMProvider(Protocol):
    async def complete(
        self,
        prompt: str,
        *,
        response_format: Literal["json", "text"] = "json",
        max_tokens: int = 4096,
        temperature: float = 0.0,
    ) -> LLMResponse: ...


class EmbeddingProvider(Protocol):
    async def embed(
        self,
        texts: list[str],
        *,
        input_type: Literal["document", "query"] = "document",
    ) -> EmbeddingResponse: ...

