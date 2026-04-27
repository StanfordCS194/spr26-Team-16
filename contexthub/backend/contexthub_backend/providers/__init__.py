from __future__ import annotations

from contexthub_backend.config import settings

from .base import EmbeddingProvider, EmbeddingResponse, LLMProvider, LLMResponse
from .factory import build_embedding_provider, build_llm_provider


def get_llm_provider(mode: str = "live") -> LLMProvider:
    return build_llm_provider(
        mode=mode,
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
    )


def get_embedding_provider(mode: str = "live") -> EmbeddingProvider:
    return build_embedding_provider(
        mode=mode,
        api_key=settings.voyage_api_key,
        model=settings.voyage_model,
    )


__all__ = [
    "LLMProvider",
    "LLMResponse",
    "EmbeddingProvider",
    "EmbeddingResponse",
    "get_llm_provider",
    "get_embedding_provider",
]
