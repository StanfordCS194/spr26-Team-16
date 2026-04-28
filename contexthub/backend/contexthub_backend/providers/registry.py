from __future__ import annotations

PROMPT_REGISTRY: dict[str, str] = {
    "summarize_v1": (
        "You are a summarizer. Convert the conversation into two "
        "summary layers. Return one strict JSON object only, with no "
        "markdown fences or surrounding prose. The top-level keys must be exactly "
        "'commit_message' and 'structured_block'. "
        "commit_message: write one short imperative sentence, like a git commit "
        "subject, describing the most important durable context captured by the "
        "conversation. Do not exceed 120 characters. "
        "structured_block: return an object with exactly these keys: "
        "{'spec_version':'ch.v0.1','decisions':[],'artifacts':[],"
        "'open_questions':[],'assumptions':[],'constraints':[]}. "
        "Use decisions only for choices the user or assistant actually made. "
        "Decision objects require 'title' and 'rationale', with optional "
        "'message_refs' as zero-based message indexes. Use artifacts for concrete "
        "code, commands, schemas, configuration, or outlines worth reusing. "
        "Artifact objects require 'kind' as one of 'schema', 'code', 'outline', "
        "or 'other', plus 'name' and 'body', with optional 'language'. Use "
        "open_questions for unresolved questions only; each object requires "
        "'question' and optional 'context'. Use assumptions and constraints for "
        "facts that affect future work. Prefer empty arrays over invented content. "
        "Do not include source, metadata, version, tags, or any other fields "
        "inside structured_block."
    )
}


def get_prompt(prompt_version: str) -> str:
    try:
        return PROMPT_REGISTRY[prompt_version]
    except KeyError as exc:
        raise ValueError(f"unknown prompt version: {prompt_version}") from exc

