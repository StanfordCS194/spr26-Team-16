from __future__ import annotations

PROMPT_REGISTRY: dict[str, str] = {
    "summarize_v1": (
        "You are ContextHub summarizer. Return strict JSON only with keys "
        "'commit_message', 'structured_block', and 'raw_transcript'. "
        "The structured_block must conform to ch.v0.1 StructuredBlockV0."
    )
}


def get_prompt(prompt_version: str) -> str:
    try:
        return PROMPT_REGISTRY[prompt_version]
    except KeyError as exc:
        raise ValueError(f"unknown prompt version: {prompt_version}") from exc

