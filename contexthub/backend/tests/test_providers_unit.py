from __future__ import annotations

import json

import pytest

from contexthub_backend.providers.fake import FakeEmbeddingProvider, FakeLLMProvider


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
    assert all(len(vector) == 3 for vector in response.vectors)
