from __future__ import annotations

import os

import pytest
import vcr

from contexthub_backend.providers.anthropic import AnthropicProvider
from contexthub_backend.providers.voyage import VoyageEmbeddingProvider


vcr_cassette = vcr.VCR(
    cassette_library_dir="tests/cassettes",
    record_mode=os.getenv("CH_VCR_RECORD_MODE", "once"),
    filter_headers=["authorization", "x-api-key"],
)


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("CH_ANTHROPIC_API_KEY"), reason="Missing CH_ANTHROPIC_API_KEY")
async def test_anthropic_provider_complete_live_recorded() -> None:
    provider = AnthropicProvider(
        api_key=os.environ["CH_ANTHROPIC_API_KEY"],
        model="claude-haiku-4-5-20251001",
    )
    with vcr_cassette.use_cassette("anthropic_complete.yaml"):
        response = await provider.complete(
            "Return JSON with keys title, details, raw_transcript.",
            response_format="json",
            max_tokens=128,
            temperature=0.0,
        )
    assert response.model
    assert response.text


@pytest.mark.live
@pytest.mark.asyncio
@pytest.mark.skipif(not os.getenv("CH_VOYAGE_API_KEY"), reason="Missing CH_VOYAGE_API_KEY")
async def test_voyage_provider_embed_live_recorded() -> None:
    provider = VoyageEmbeddingProvider(
        api_key=os.environ["CH_VOYAGE_API_KEY"],
        model="voyage-3-large",
    )
    with vcr_cassette.use_cassette("voyage_embed.yaml"):
        response = await provider.embed(["hello world"], input_type="document")
    assert response.model == "voyage-3-large"
    assert len(response.vectors) == 1
    assert len(response.vectors[0]) == 1024
