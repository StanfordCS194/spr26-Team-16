from __future__ import annotations

from .base import EmbeddingProvider, LLMProvider
from .anthropic import AnthropicProvider
from .fake import FakeEmbeddingProvider, FakeLLMProvider
from .vercel_gateway import VercelGatewayEmbeddingProvider, VercelGatewayLLMProvider
from .voyage import VoyageEmbeddingProvider


def build_llm_provider(
    *,
    mode: str,
    api_key: str | None,
    model: str,
    ai_gateway_api_key: str | None = None,
    ai_gateway_base_url: str = "https://ai-gateway.vercel.sh/v1",
    ai_gateway_model: str | None = None,
    ai_gateway_json_mode: bool = False,
) -> LLMProvider:
    if mode == "fake":
        return FakeLLMProvider()
    if ai_gateway_api_key:
        return VercelGatewayLLMProvider(
            api_key=ai_gateway_api_key,
            base_url=ai_gateway_base_url,
            model=ai_gateway_model or model,
            prompt_version="summarize_v1",
            json_mode=ai_gateway_json_mode,
        )
    if not api_key:
        raise ValueError("Missing Anthropic API key for live provider.")
    return AnthropicProvider(api_key=api_key, model=model, prompt_version="summarize_v1")


def build_embedding_provider(
    *,
    mode: str,
    api_key: str | None,
    model: str,
    ai_gateway_api_key: str | None = None,
    ai_gateway_base_url: str = "https://ai-gateway.vercel.sh/v1",
    ai_gateway_model: str | None = None,
    ai_gateway_target_dimensions: int | None = None,
) -> EmbeddingProvider:
    if mode == "fake":
        return FakeEmbeddingProvider()
    if ai_gateway_api_key:
        return VercelGatewayEmbeddingProvider(
            api_key=ai_gateway_api_key,
            base_url=ai_gateway_base_url,
            model=ai_gateway_model or model,
            target_dimensions=ai_gateway_target_dimensions,
        )
    if not api_key:
        raise ValueError("Missing Voyage API key for live embedding provider.")
    return VoyageEmbeddingProvider(api_key=api_key, model=model)

