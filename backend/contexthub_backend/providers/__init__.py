from __future__ import annotations

from contexthub_backend.config import settings

from .base import EmbeddingProvider, EmbeddingResponse, LLMProvider, LLMResponse
from .factory import build_embedding_provider, build_llm_provider


def get_llm_provider(mode: str = "live") -> LLMProvider:
    return build_llm_provider(
        mode=mode,
        api_key=settings.anthropic_api_key,
        model=settings.anthropic_model,
        ai_gateway_api_key=settings.ai_gateway_api_key,
        ai_gateway_base_url=settings.ai_gateway_base_url,
        ai_gateway_model=settings.ai_gateway_llm_model,
        ai_gateway_json_mode=settings.ai_gateway_json_mode,
    )


def get_embedding_provider(mode: str = "live") -> EmbeddingProvider:
    return build_embedding_provider(
        mode=mode,
        api_key=settings.voyage_api_key,
        model=settings.voyage_model,
        ai_gateway_api_key=settings.ai_gateway_api_key,
        ai_gateway_base_url=settings.ai_gateway_base_url,
        ai_gateway_model=settings.ai_gateway_embedding_model,
        ai_gateway_target_dimensions=settings.ai_gateway_embedding_dimensions,
    )


__all__ = [
    "LLMProvider",
    "LLMResponse",
    "EmbeddingProvider",
    "EmbeddingResponse",
    "get_llm_provider",
    "get_embedding_provider",
]
