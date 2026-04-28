import json
import os
from pathlib import Path

from openai import OpenAI

EXTRACTION_PROMPT = """You are extracting structured context from a conversation between a user and an AI assistant. Your output will be used in two ways:

1. As an INDEX CARD — helping someone quickly scan whether this conversation is relevant to what they're working on
2. As CONTINUATION CONTEXT — giving someone (or an AI) enough information to pick up where this conversation left off

EXTRACT THE FOLLOWING:

## title
A specific, descriptive title (5-12 words). Should distinguish this conversation from others on similar topics.
- Bad: "Coding Help" or "Marketing Discussion"
- Good: "JWT Auth System Design with Refresh Token Rotation"
- Good: "Series A Pitch Deck Narrative and Structure"

## conversation_type
Categorize the conversation. Pick ONE primary type:
- "decision" — evaluating options, making a choice
- "build" — creating something (code, doc, design, plan)
- "research" — exploring a topic, gathering information
- "brainstorm" — generating ideas, creative exploration
- "debug" — diagnosing and fixing a problem
- "planning" — organizing work, setting priorities
- "learning" — understanding a concept or skill
- "writing" — drafting or editing text content
- "other" — doesn't fit above categories

## summary
3-5 sentences capturing:
- What problem or question started the conversation
- What direction it went
- Where it ended up (conclusion, output, or current state)

Write this as a briefing for someone who needs to decide whether to read the full conversation. Prioritize OUTCOMES over process.

## key_takeaways
An array of the 3-7 most important things that came out of this conversation. These should be the things you'd want to remember a week from now. Each takeaway should be one clear sentence.

What counts as a takeaway depends on the conversation type:
- For decisions: the choice made AND the key reason why
- For building: the design choices and tradeoffs
- For research: the most important findings or insights
- For brainstorms: the strongest ideas that emerged
- For debugging: root cause and fix
- For planning: the priorities and key milestones
- For learning: the core concepts or mental models
- For writing: the framing decisions and key messaging choices

Do NOT include things that were merely discussed but not concluded. If the conversation was exploratory with no clear conclusions, capture the most important INSIGHTS instead.

## artifacts
An array of concrete, reusable outputs produced during the conversation. Only include substantial artifacts — things someone might want to copy, reference, or build on.

Each artifact:
- "type": "code" | "config" | "template" | "outline" | "framework" | "prompt" | "data" | "other"
- "language": programming language if code (e.g., "python", "javascript", "sql"), null otherwise
- "description": one-line description of what this is and when you'd use it
- "content": the FULL content — never truncate code or templates

If the conversation produced no reusable artifacts, return an empty array.

## open_threads
An array of unresolved items — things that were raised but not finished, flagged for follow-up, or explicitly left as next steps. Each should be phrased as a clear question or action item.

If everything was resolved, return an empty array.

## tags
An array of 3-8 keywords/topics for searchability. Include specific technologies, domain concepts, project names — terms someone would actually search for.

CRITICAL GUIDELINES:
- Be concise. Every sentence should earn its place.
- Optimize for SCANNING — someone should get the gist in 10 seconds.
- key_takeaways is the most important field. Get this right.
- Don't editorialize or add your own opinions — just extract what's there.
- If the conversation is short or trivial, it's fine to have sparse output. Don't inflate.
- Artifacts should include FULL content, never truncated.

Return ONLY valid JSON with this exact structure (no markdown fencing, no explanation):
{
  "title": "string",
  "conversation_type": "string",
  "summary": "string",
  "key_takeaways": ["string"],
  "artifacts": [{"type": "string", "language": "string|null", "description": "string", "content": "string"}],
  "open_threads": ["string"],
  "tags": ["string"]
}"""

VALID_CONVERSATION_TYPES = {
    "decision", "build", "research", "brainstorm", "debug",
    "planning", "learning", "writing", "other",
}

TRANSCRIPT_DIR = Path("data/transcripts")


def format_conversation(messages: list[dict]) -> str:
    """Format a list of messages into a readable conversation string."""
    lines = []
    for msg in messages:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role_label}: {msg['content']}")
    return "\n\n".join(lines)


def save_transcript(thread_id: str, messages: list[dict]) -> str:
    """Save raw conversation messages to a JSON file. Returns the file path."""
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPT_DIR / f"{thread_id}.json"
    with open(path, "w") as f:
        json.dump(messages, f, indent=2)
    return str(path)


def load_transcript(transcript_path: str) -> list[dict]:
    """Load raw messages from a transcript file."""
    with open(transcript_path, "r") as f:
        return json.load(f)


def extract_context(messages: list[dict]) -> dict:
    """
    Send the conversation to OpenAI and get structured extraction.

    Returns dict with: title, conversation_type, summary, key_takeaways,
    artifacts, open_threads, tags

    Raises:
        ValueError: If the API response can't be parsed as valid JSON
        openai.OpenAIError: If the API call fails
    """
    conversation_text = format_conversation(messages)

    client = OpenAI()

    response = client.chat.completions.create(
        model="gpt-4o",
        max_tokens=8192,
        response_format={"type": "json_object"},
        messages=[
            {
                "role": "user",
                "content": f"{EXTRACTION_PROMPT}\n\nCONVERSATION:\n---\n{conversation_text}\n---",
            }
        ],
    )

    raw_text = response.choices[0].message.content

    # Strip markdown fences if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]
        raw_text = raw_text.rsplit("```", 1)[0]
    raw_text = raw_text.strip()

    try:
        extracted = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(
            f"Extraction returned invalid JSON: {e}\nRaw response: {raw_text[:500]}"
        )

    # Validate and set defaults
    required_strings = {
        "title": "Untitled Conversation",
        "conversation_type": "other",
        "summary": "",
    }
    required_arrays = ["key_takeaways", "artifacts", "open_threads", "tags"]

    for field, default in required_strings.items():
        if field not in extracted or not isinstance(extracted[field], str):
            extracted[field] = default

    for field in required_arrays:
        if field not in extracted or not isinstance(extracted[field], list):
            extracted[field] = []

    # Validate conversation_type
    if extracted["conversation_type"] not in VALID_CONVERSATION_TYPES:
        extracted["conversation_type"] = "other"

    # Validate artifact structure
    validated_artifacts = []
    for artifact in extracted["artifacts"]:
        if isinstance(artifact, dict) and "content" in artifact:
            validated_artifacts.append({
                "type": artifact.get("type", "other"),
                "language": artifact.get("language"),
                "description": artifact.get("description", "Untitled artifact"),
                "content": artifact["content"],
            })
    extracted["artifacts"] = validated_artifacts

    return extracted


def extract_context_mock(messages: list[dict]) -> dict:
    """Returns dummy extraction data for development without an API key."""
    return {
        "title": f"Conversation ({len(messages)} messages)",
        "conversation_type": "other",
        "summary": f"A conversation with {len(messages)} messages. Set OPENAI_API_KEY to enable real extraction.",
        "key_takeaways": [
            "This is mock extraction data",
            "Set OPENAI_API_KEY to enable real extraction",
        ],
        "artifacts": [],
        "open_threads": ["Enable real extraction by adding API key"],
        "tags": ["mock", "development"],
    }


def process_thread(thread_id: str, messages: list[dict], use_mock: bool = False) -> dict:
    """
    Full extraction pipeline:
    1. Save the raw transcript
    2. Run extraction (real or mock)
    3. Return all data needed to update the database

    Returns dict with all fields needed for the threads table update.
    """
    transcript_path = save_transcript(thread_id, messages)

    if use_mock or not os.environ.get("OPENAI_API_KEY"):
        extracted = extract_context_mock(messages)
    else:
        extracted = extract_context(messages)

    return {
        "title": extracted["title"],
        "conversation_type": extracted["conversation_type"],
        "summary": extracted["summary"],
        "key_takeaways": json.dumps(extracted["key_takeaways"]),
        "artifacts": json.dumps(extracted["artifacts"]),
        "open_threads": json.dumps(extracted["open_threads"]),
        "tags": json.dumps(extracted["tags"]),
        "raw_transcript_path": transcript_path,
        "extraction_status": "done",
        "message_count": len(messages),
    }


def validate_extraction(extracted: dict) -> list[str]:
    """Returns a list of warnings (empty = all good)."""
    warnings = []

    if not extracted.get("title") or len(extracted["title"]) < 5:
        warnings.append("Title is missing or too short")

    if len(extracted.get("title", "")) > 80:
        warnings.append("Title is unusually long (>80 chars)")

    if not extracted.get("summary") or len(extracted["summary"]) < 30:
        warnings.append("Summary is missing or too short")

    if not extracted.get("key_takeaways") or len(extracted["key_takeaways"]) == 0:
        warnings.append("No key takeaways extracted")

    if len(extracted.get("key_takeaways", [])) > 10:
        warnings.append("Too many takeaways (>10) — extraction may be inflating")

    if extracted.get("conversation_type") not in VALID_CONVERSATION_TYPES:
        warnings.append(f"Invalid conversation_type: {extracted.get('conversation_type')}")

    if not extracted.get("tags") or len(extracted["tags"]) < 2:
        warnings.append("Too few tags for searchability")

    for i, artifact in enumerate(extracted.get("artifacts", [])):
        if not artifact.get("content"):
            warnings.append(f"Artifact {i} has no content")
        if artifact.get("content") and artifact["content"].endswith("..."):
            warnings.append(f"Artifact {i} appears truncated (ends with '...')")

    return warnings
