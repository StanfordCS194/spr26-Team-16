from __future__ import annotations

from .base import EmbeddingProvider, LLMProvider
from .anthropic import AnthropicProvider
from .fake import FakeEmbeddingProvider, FakeLLMProvider
from .voyage import VoyageEmbeddingProvider


def build_llm_provider(*, mode: str, api_key: str | None, model: str) -> LLMProvider:
    if mode == "fake":
        return FakeLLMProvider()
    if not api_key:
        raise ValueError("Missing Anthropic API key for live provider.")
    return AnthropicProvider(api_key=api_key, model=model, prompt_version="summarize_v1")


def build_embedding_provider(
    *, mode: str, api_key: str | None, model: str
) -> EmbeddingProvider:
    if mode == "fake":
        return FakeEmbeddingProvider()
    if not api_key:
        raise ValueError("Missing Voyage API key for live embedding provider.")
    return VoyageEmbeddingProvider(api_key=api_key, model=model)

