from __future__ import annotations

from dataclasses import dataclass
import json

from pydantic import BaseModel, Field, ValidationError as PydanticValidationError

from contexthub_interchange.models import ConversationV0

from contexthub_backend.providers.base import LLMProvider
from contexthub_backend.providers.registry import get_prompt


class SummaryDetails(BaseModel):
    summary: str
    key_takeaways: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


@dataclass(slots=True)
class ThreeLayerSummary:
    title: str
    summary: str
    details: SummaryDetails
    raw_transcript: str
    model: str
    prompt_version: str
    input_tokens: int
    output_tokens: int
    latency_ms: int
    cost_usd: float
    failure_reason: str | None = None


def _fallback_title(conversation: ConversationV0) -> str:
    for msg in conversation.messages:
        for content in msg.content:
            text = getattr(content.root, "text", "")
            if text:
                return f"Fallback summary: {text[:120]}"
    return "Fallback summary: conversation captured."

def _build_prompt(conversation: ConversationV0, prompt_version: str) -> str:
    prompt = get_prompt(prompt_version)
    conversation_json = json.dumps(conversation.model_dump(mode="json"), sort_keys=True)
    return f"{prompt}\nConversation JSON:\n{conversation_json}"


def _extract_json_object(text: str) -> dict:
    stripped = text.strip()
    if stripped.startswith("```"):
        lines = stripped.splitlines()
        if lines and lines[0].startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].startswith("```"):
            lines = lines[:-1]
        stripped = "\n".join(lines).strip()
    try:
        return json.loads(stripped)
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start == -1 or end == -1 or end <= start:
            raise
        return json.loads(stripped[start : end + 1])


async def summarize_push(
    conversation: ConversationV0,
    *,
    llm: LLMProvider,
    prompt_version: str,
) -> ThreeLayerSummary:
    failure_reason: str | None = None
    for _ in range(3):
        response = await llm.complete(
            _build_prompt(conversation, prompt_version),
            response_format="json",
            max_tokens=4096,
            temperature=0.1,
        )
        try:
            payload = _extract_json_object(response.text)
            details = SummaryDetails.model_validate(payload["details"])
            return ThreeLayerSummary(
                title=str(payload["title"]).strip(),
                summary=details.summary.strip(),
                details=details,
                raw_transcript="",
                model=response.model,
                prompt_version=response.prompt_version,
                input_tokens=response.input_tokens,
                output_tokens=response.output_tokens,
                latency_ms=response.latency_ms,
                cost_usd=response.cost_usd,
                failure_reason=response.failure_reason,
            )
        except (KeyError, TypeError, json.JSONDecodeError, PydanticValidationError) as exc:
            snippet = response.text[:500].replace("\n", "\\n")
            failure_reason = f"invalid_summary_json: {exc}; response_snippet={snippet}"

    fallback_details = SummaryDetails(
        summary="Summary unavailable.",
        key_takeaways=["Summary generation failed."],
        tags=["context", "fallback", "review", "follow-up"],
    )
    return ThreeLayerSummary(
        title=_fallback_title(conversation),
        summary=fallback_details.summary,
        details=fallback_details,
        raw_transcript="",
        model="fallback",
        prompt_version=prompt_version,
        input_tokens=0,
        output_tokens=0,
        latency_ms=0,
        cost_usd=0.0,
        failure_reason=failure_reason,
    )

