from __future__ import annotations

PROMPT_REGISTRY: dict[str, str] = {
    "summarize_v1": (
        "You are a summarizer. Convert the conversation into two "
        "summary layers. Return one strict JSON object only, with no "
        "markdown fences or surrounding prose. The top-level keys must be exactly "
        "'title' and 'details'. "
        "title: write one short imperative sentence, like a git commit subject, "
        "describing the most important durable context captured by the conversation. "
        "Do not exceed 120 characters. "
        "details: return an object with exactly these keys: "
        "{'summary':'','key_takeaways':[],'tags':[]}. "
        "summary must be a concise product-ready paragraph for the push list. "
        "key_takeaways must contain concise bullet-style strings capturing durable "
        "decisions, artifacts, assumptions, constraints, or unresolved questions. "
        "tags must contain 4-5 short lowercase tags. Prefer empty key_takeaways over "
        "invented content, but always include a useful summary and tags."
    )
}


def get_prompt(prompt_version: str) -> str:
    try:
        return PROMPT_REGISTRY[prompt_version]
    except KeyError as exc:
        raise ValueError(f"unknown prompt version: {prompt_version}") from exc

