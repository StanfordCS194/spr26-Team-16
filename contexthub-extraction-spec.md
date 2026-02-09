# ContextHub Extraction System — Full Specification

> This document is the complete spec for ContextHub's extraction system. It covers the extraction prompt, the Python implementation, the database schema it writes to, the pull context formats, and how to test it. This is everything needed to build `extraction.py` and the `/context` endpoint.

---

## 1. What This System Does

When a user pushes a conversation from Claude, the backend receives the raw messages and needs to:

1. Store the raw transcript as a JSON file
2. Send the conversation to Claude Sonnet 4.5 with an extraction prompt
3. Parse the structured JSON response
4. Store the extracted fields in SQLite
5. Serve two pull formats: summary context and full transcript

The extraction turns a raw conversation into a structured index that's findable, scannable, and resumable.

---

## 2. Database Schema

The extraction writes to the `threads` table. Here are the columns the extraction system is responsible for populating:

```sql
CREATE TABLE IF NOT EXISTS threads (
  id TEXT PRIMARY KEY,
  source TEXT NOT NULL DEFAULT 'claude',
  source_url TEXT,

  -- Extracted content (populated by extraction.py)
  title TEXT,
  conversation_type TEXT,         -- "decision" | "build" | "research" | "brainstorm" | "debug" | "planning" | "learning" | "writing" | "other"
  summary TEXT,
  key_takeaways TEXT,             -- JSON array of strings
  artifacts TEXT,                 -- JSON array of {type, language, description, content}
  open_threads TEXT,              -- JSON array of strings
  tags TEXT,                      -- JSON array of strings

  -- Raw storage
  raw_transcript_path TEXT,       -- Path to JSON file with full messages
  extraction_status TEXT DEFAULT 'pending',  -- "pending" | "processing" | "done" | "failed"
  message_count INTEGER,

  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);
```

**Storage notes:**
- `key_takeaways`, `artifacts`, `open_threads`, and `tags` are stored as JSON strings (use `json.dumps()` before writing, `json.loads()` when reading)
- `raw_transcript_path` points to a JSON file in `./data/transcripts/{thread_id}.json` containing the original `[{role, content}]` array
- `extraction_status` should be set to `"processing"` when extraction starts, `"done"` on success, `"failed"` on error

---

## 3. The Extraction Prompt

This is the exact prompt to send to Claude Sonnet 4.5. It goes in the `user` message, followed by the formatted conversation.

```
You are extracting structured context from a conversation between a user and an AI assistant. Your output will be used in two ways:

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

Common artifacts: code snippets, SQL queries, API schemas, email drafts, frameworks/matrices, prompt templates, configuration files, data structures.

If the conversation produced no reusable artifacts, return an empty array.

## open_threads
An array of unresolved items — things that were raised but not finished, flagged for follow-up, or explicitly left as next steps. Each should be phrased as a clear question or action item.

This is critical for conversation CONTINUATION. Someone pulling this context should immediately know what still needs to be done.

If everything was resolved, return an empty array.

## tags
An array of 3-8 keywords/topics for searchability. Include:
- Specific technologies, tools, or frameworks mentioned
- Domain concepts (e.g., "authentication", "pricing", "onboarding")
- Project names if mentioned
- The general category (e.g., "backend", "strategy", "design")

These are used for search and filtering — pick terms someone would actually search for.

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
}
```

---

## 4. Python Implementation

### File: `extraction.py`

```python
import anthropic
import json
import os
import uuid
from pathlib import Path

# The extraction prompt — see Section 3 for the full annotated version
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


# --- Transcript Storage ---

TRANSCRIPT_DIR = Path("./data/transcripts")

def save_transcript(thread_id: str, messages: list[dict]) -> str:
    """
    Save the raw conversation messages to a JSON file.
    Returns the file path (relative to project root).
    """
    TRANSCRIPT_DIR.mkdir(parents=True, exist_ok=True)
    path = TRANSCRIPT_DIR / f"{thread_id}.json"
    with open(path, "w") as f:
        json.dump(messages, f, indent=2)
    return str(path)


def load_transcript(transcript_path: str) -> list[dict]:
    """
    Load raw messages from a transcript file.
    Returns list of {role, content} dicts.
    """
    with open(transcript_path, "r") as f:
        return json.load(f)


# --- Extraction ---

def format_conversation(messages: list[dict]) -> str:
    """
    Format a list of messages into a readable conversation string
    for the extraction prompt.
    """
    lines = []
    for msg in messages:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        lines.append(f"{role_label}: {msg['content']}")
    return "\n\n".join(lines)


def extract_context(messages: list[dict]) -> dict:
    """
    Send the conversation to Claude Sonnet 4.5 and get structured extraction.

    Args:
        messages: List of {role: "user"|"assistant", content: "..."} dicts

    Returns:
        Dict with keys: title, conversation_type, summary, key_takeaways,
        artifacts, open_threads, tags

    Raises:
        ValueError: If the API response can't be parsed as valid JSON
        anthropic.APIError: If the API call fails
    """
    conversation_text = format_conversation(messages)

    client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var

    response = client.messages.create(
        model="claude-sonnet-4-5-20250514",
        max_tokens=8192,
        messages=[
            {
                "role": "user",
                "content": f"{EXTRACTION_PROMPT}\n\nCONVERSATION:\n---\n{conversation_text}\n---"
            }
        ]
    )

    raw_text = response.content[0].text

    # Clean up markdown fencing if present
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]
        raw_text = raw_text.rsplit("```", 1)[0]
    raw_text = raw_text.strip()

    try:
        extracted = json.loads(raw_text)
    except json.JSONDecodeError as e:
        raise ValueError(f"Extraction returned invalid JSON: {e}\nRaw response: {raw_text[:500]}")

    # Validate and set defaults for missing fields
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

    # Validate conversation_type is a known value
    valid_types = {"decision", "build", "research", "brainstorm", "debug", "planning", "learning", "writing", "other"}
    if extracted["conversation_type"] not in valid_types:
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


# --- Mock Extraction (for development without API key) ---

def extract_context_mock(messages: list[dict]) -> dict:
    """
    Returns dummy extraction data for development/testing.
    Use this when you don't want to hit the Claude API.
    """
    return {
        "title": f"Conversation ({len(messages)} messages)",
        "conversation_type": "other",
        "summary": f"A conversation with {len(messages)} messages. Replace this with real extraction by setting ANTHROPIC_API_KEY.",
        "key_takeaways": [
            "This is mock extraction data",
            "Set ANTHROPIC_API_KEY to enable real extraction"
        ],
        "artifacts": [],
        "open_threads": ["Enable real extraction by adding API key"],
        "tags": ["mock", "development"]
    }


# --- Main entry point for the backend to call ---

def process_thread(thread_id: str, messages: list[dict], use_mock: bool = False) -> dict:
    """
    Full extraction pipeline:
    1. Save the raw transcript
    2. Run extraction (real or mock)
    3. Return all data needed to update the database

    Args:
        thread_id: UUID for this thread
        messages: Raw conversation messages [{role, content}]
        use_mock: If True, skip the API call and return mock data

    Returns:
        Dict with all fields needed for the threads table update
    """
    # Save raw transcript
    transcript_path = save_transcript(thread_id, messages)

    # Run extraction
    if use_mock or not os.environ.get("ANTHROPIC_API_KEY"):
        extracted = extract_context_mock(messages)
    else:
        extracted = extract_context(messages)

    # Return everything the database needs
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
```

### How the backend should call this

In your FastAPI route handler for `POST /api/threads`:

```python
from extraction import process_thread
import uuid

@app.post("/api/threads")
async def create_thread(data: dict):
    thread_id = str(uuid.uuid4())
    messages = data["messages"]

    # Update status to processing
    # db.execute("UPDATE threads SET extraction_status = 'processing' WHERE id = ?", (thread_id,))

    try:
        result = process_thread(thread_id, messages)
        # Insert into database with all extracted fields
        # db.execute("INSERT INTO threads (id, source, source_url, title, ...) VALUES (?, ?, ?, ?, ...)", ...)
        return {"id": thread_id, **result}
    except Exception as e:
        # db.execute("UPDATE threads SET extraction_status = 'failed' WHERE id = ?", (thread_id,))
        raise HTTPException(status_code=500, detail=str(e))
```

---

## 5. Pull Context Formats

These are the two formats served by `GET /api/threads/{id}/context`. The user copies one of these to paste into a new LLM session.

### 5.1 Summary Pull (default)

Returned by `GET /api/threads/{id}/context` or `GET /api/threads/{id}/context?format=summary`

```python
def format_summary_context(thread: dict) -> str:
    """
    Format extracted thread data into a compact context block
    for pasting into a new LLM session.

    Args:
        thread: Dict with title, summary, key_takeaways, artifacts,
                open_threads (all already parsed from JSON)
    """
    output = "[Context from ContextHub]\n"
    output += f"Continuing from a previous conversation: {thread['title']}\n\n"
    output += f"{thread['summary']}\n"

    takeaways = thread.get("key_takeaways", [])
    if takeaways:
        output += "\nKey takeaways:\n"
        for t in takeaways:
            output += f"- {t}\n"

    open_threads = thread.get("open_threads", [])
    if open_threads:
        output += "\nStill open:\n"
        for t in open_threads:
            output += f"- {t}\n"

    artifacts = thread.get("artifacts", [])
    if artifacts and len(artifacts) <= 3:
        output += "\nArtifacts from that conversation:\n"
        for a in artifacts:
            lang = a.get("language") or ""
            output += f"[{a['description']}]\n```{lang}\n{a['content']}\n```\n"
    elif artifacts and len(artifacts) > 3:
        output += f"\nNote: {len(artifacts)} artifacts were produced. Ask me to share specific ones if needed.\n"

    output += "[End Context]"
    return output
```

**Example output:**

```
[Context from ContextHub]
Continuing from a previous conversation: JWT Auth System Design with Refresh Token Rotation

Started by exploring authentication options for a new web app. Compared JWT vs session-based auth, weighing statelessness and scalability against simplicity. Landed on JWT with refresh token rotation as the best tradeoff for horizontal scaling.

Key takeaways:
- JWT over session-based auth — stateless architecture scales better for horizontal deployment
- 15-minute access tokens with 7-day refresh tokens balances security and UX
- Store refresh tokens in httpOnly cookies, never localStorage
- Refresh token rotation (one-time use) prevents replay attacks without server-side tracking

Still open:
- How to handle token revocation at scale — Redis blacklist vs short expiry?
- Rate limiting strategy for auth endpoints — per-IP or per-user?

Artifacts from that conversation:
[Token generation and refresh utility for Express.js]
```javascript
const jwt = require('jsonwebtoken');

const generateTokens = (userId) => {
  const accessToken = jwt.sign({ userId }, process.env.ACCESS_SECRET, { expiresIn: '15m' });
  const refreshToken = jwt.sign({ userId }, process.env.REFRESH_SECRET, { expiresIn: '7d' });
  return { accessToken, refreshToken };
};
```
[End Context]
```

### 5.2 Full Transcript Pull

Returned by `GET /api/threads/{id}/context?format=full`

```python
def format_full_context(thread: dict, messages: list[dict]) -> str:
    """
    Format extracted thread data + full raw transcript for pasting
    into a new LLM session.

    Args:
        thread: Dict with title, summary, key_takeaways, open_threads
        messages: Raw conversation messages [{role, content}]
    """
    output = "[Full conversation from ContextHub]\n"
    output += f"This is a complete transcript of a previous conversation: {thread['title']}\n\n"
    output += f"Summary: {thread['summary']}\n"

    takeaways = thread.get("key_takeaways", [])
    if takeaways:
        output += "\nKey takeaways:\n"
        for t in takeaways:
            output += f"- {t}\n"

    open_threads = thread.get("open_threads", [])
    if open_threads:
        output += "\nStill open:\n"
        for t in open_threads:
            output += f"- {t}\n"

    output += "\n--- Full Transcript ---\n"
    for msg in messages:
        role = "User" if msg["role"] == "user" else "Assistant"
        output += f"{role}: {msg['content']}\n\n"
    output += "--- End Transcript ---\n"
    output += "[End Context]"
    return output
```

### 5.3 Context API Endpoint

```python
from extraction import load_transcript

@app.get("/api/threads/{thread_id}/context")
async def get_context(thread_id: str, format: str = "summary"):
    """
    Returns formatted context ready to paste into a new LLM session.

    Query params:
        format: "summary" (default) or "full"
    """
    # Fetch thread from database
    thread = get_thread_from_db(thread_id)  # Your DB fetch function
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")

    # Parse JSON fields
    thread_data = {
        "title": thread["title"],
        "summary": thread["summary"],
        "key_takeaways": json.loads(thread["key_takeaways"] or "[]"),
        "artifacts": json.loads(thread["artifacts"] or "[]"),
        "open_threads": json.loads(thread["open_threads"] or "[]"),
    }

    if format == "full":
        # Load raw transcript from file
        messages = load_transcript(thread["raw_transcript_path"])
        formatted = format_full_context(thread_data, messages)
        token_estimate = len(formatted) // 4  # Rough estimate
        return {
            "formatted_context": formatted,
            "format": "full",
            "estimated_tokens": token_estimate,
        }
    else:
        formatted = format_summary_context(thread_data)
        return {
            "formatted_context": formatted,
            "format": "summary",
        }
```

---

## 6. Extraction Field Reference

Quick reference for what each field is and what good vs bad looks like.

### title
| Good | Bad |
|------|-----|
| "JWT Auth System Design with Refresh Token Rotation" | "Auth Discussion" |
| "PostgreSQL vs MongoDB for E-Commerce Product Catalog" | "Database Help" |
| "Series A Pitch Deck Narrative and Investor Framing" | "Pitch Deck" |

### conversation_type
One of: `decision`, `build`, `research`, `brainstorm`, `debug`, `planning`, `learning`, `writing`, `other`

### summary
| Good | Bad |
|------|-----|
| "Started by exploring auth options for a new web app. Compared JWT vs sessions, weighing scalability against simplicity. Landed on JWT with refresh token rotation." | "The user asked about authentication and the assistant helped them." |

### key_takeaways
| Good | Bad |
|------|-----|
| "JWT over sessions because stateless architecture scales better for horizontal deployment" | "Discussed JWT vs sessions" |
| "Root cause was a race condition in the connection pool — fixed by adding mutex around pool.acquire()" | "Found and fixed a bug" |

### artifacts
- Must include FULL `content` — never truncated
- `type` must be one of: `code`, `config`, `template`, `outline`, `framework`, `prompt`, `data`, `other`
- `language` is the programming language string (e.g., `"python"`, `"javascript"`, `"sql"`) or `null`

### open_threads
| Good | Bad |
|------|-----|
| "How to handle token revocation at scale — Redis blacklist vs short expiry?" | "Need to think about revocation" |
| "Write integration tests for the auth middleware before deploying" | "Testing" |

### tags
| Good | Bad |
|------|-----|
| `["JWT", "Express", "authentication", "refresh-tokens", "backend"]` | `["programming", "technology", "web"]` |

---

## 7. Testing

### Manual Testing Checklist

Test the extraction against at least one conversation of each type:

| # | Conversation type | What to verify |
|---|-------------------|---------------|
| 1 | Decision ("should we use X or Y?") | `key_takeaways` captures the choice AND the reasoning, not just "decided on X" |
| 2 | Build (coding session) | All code artifacts are complete, not truncated. Takeaways are about design choices. |
| 3 | Research/exploration (no firm conclusion) | Handles ambiguity gracefully. Takeaways are insightful, not vague. |
| 4 | Short/simple (3-4 messages) | Output is proportionally sparse. No inflation or padding. |
| 5 | Long/meandering (30+ messages) | Summary finds the signal. Not a play-by-play. |

### Automated Validation

After each extraction, validate the output programmatically:

```python
def validate_extraction(extracted: dict) -> list[str]:
    """
    Returns a list of warnings (empty = all good).
    """
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

    valid_types = {"decision", "build", "research", "brainstorm", "debug", "planning", "learning", "writing", "other"}
    if extracted.get("conversation_type") not in valid_types:
        warnings.append(f"Invalid conversation_type: {extracted.get('conversation_type')}")

    if not extracted.get("tags") or len(extracted["tags"]) < 2:
        warnings.append("Too few tags for searchability")

    # Check artifacts have content
    for i, artifact in enumerate(extracted.get("artifacts", [])):
        if not artifact.get("content"):
            warnings.append(f"Artifact {i} has no content")
        if artifact.get("content") and artifact["content"].endswith("..."):
            warnings.append(f"Artifact {i} appears truncated (ends with '...')")

    return warnings
```

### Pull Format Testing

After building the pull format functions, test by:

1. Extract context from a real conversation
2. Copy the summary pull output
3. Paste it into a new Claude conversation
4. Ask Claude to continue the work
5. Verify Claude responds with actual context from the prior conversation — not generic responses

This is the real test of whether the extraction + pull format is working.

---

## 8. Environment Setup

```bash
# Required
export ANTHROPIC_API_KEY="sk-ant-..."

# The extraction uses Claude Sonnet 4.5
# Model string: claude-sonnet-4-5-20250514
# Max tokens for extraction response: 8192
# Typical extraction cost: $0.01-0.05 per conversation (depends on length)
```

If `ANTHROPIC_API_KEY` is not set, `process_thread()` automatically falls back to mock extraction so development can continue without an API key.

---

## 9. File Structure

```
backend/
├── extraction.py          # Everything in this document
├── data/
│   └── transcripts/       # Raw conversation JSON files
│       ├── {thread_id}.json
│       └── ...
```

The `data/transcripts/` directory is created automatically by `save_transcript()` on first use.
