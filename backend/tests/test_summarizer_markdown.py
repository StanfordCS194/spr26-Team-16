import pytest

from contexthub_interchange.models import ConversationV0

from contexthub_backend.providers.fake import FakeLLMProvider
from contexthub_backend.services.summarizer import summarize_push


@pytest.mark.asyncio
async def test_summarize_push_returns_llm_generated_product_sections() -> None:
    conversation = ConversationV0.model_validate(
        {
            "spec_version": "ch.v0.1",
            "source": {"platform": "claude_ai", "captured_at": "2026-04-28T00:00:00Z"},
            "messages": [
                {
                    "role": "user",
                    "content": [{"type": "text", "text": "Summarize decisions and key takeaways."}],
                }
            ],
            "metadata": {"title": "Search quality improvements"},
        }
    )

    result = await summarize_push(conversation, llm=FakeLLMProvider(), prompt_version="summarize_v1")

    assert result.title.startswith("Summary:")
    assert result.details.summary
    assert result.details.key_takeaways
    assert len(result.details.tags) == 4
