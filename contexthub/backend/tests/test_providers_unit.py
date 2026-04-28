from __future__ import annotations

import json

import pytest

from contexthub_backend.providers.fake import FakeEmbeddingProvider, FakeLLMProvider
from contexthub_backend.providers.factory import (
    build_embedding_provider,
    build_llm_provider,
)
from contexthub_backend.providers.vercel_gateway import (
    VercelGatewayEmbeddingProvider,
    VercelGatewayLLMProvider,
    _resize_vector,
)


@pytest.mark.asyncio
async def test_fake_llm_complete_json_response() -> None:
    provider = FakeLLMProvider()
    response = await provider.complete("summarize this conversation", response_format="json")
    payload = json.loads(response.text)
    assert payload["commit_message"].startswith("Summary:")
    assert "structured_block" in payload


@pytest.mark.asyncio
async def test_fake_embedding_embed_returns_vectors() -> None:
    provider = FakeEmbeddingProvider()
    response = await provider.embed(["alpha", "beta"], input_type="document")
    assert len(response.vectors) == 2
    assert all(len(vector) == 1024 for vector in response.vectors)


def test_factory_prefers_vercel_gateway_for_llm_when_configured() -> None:
    provider = build_llm_provider(
        mode="live",
        api_key=None,
        model="claude-haiku-4-5-20251001",
        ai_gateway_api_key="test-gateway-key",
        ai_gateway_model="anthropic/claude-opus-4.6",
    )
    assert isinstance(provider, VercelGatewayLLMProvider)


def test_factory_prefers_vercel_gateway_for_embeddings_when_configured() -> None:
    provider = build_embedding_provider(
        mode="live",
        api_key=None,
        model="voyage-3-large",
        ai_gateway_api_key="test-gateway-key",
        ai_gateway_model="voyage/voyage-3-large",
    )
    assert isinstance(provider, VercelGatewayEmbeddingProvider)


def test_vercel_gateway_embedding_vectors_resize_to_target_dimensions() -> None:
    assert _resize_vector([1.0, 2.0], 4) == [1.0, 2.0, 0.0, 0.0]
    assert _resize_vector([1.0, 2.0, 3.0], 2) == [1.0, 2.0]
    assert _resize_vector([1.0], None) == [1.0]
