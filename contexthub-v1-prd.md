# ContextHub V1 MVP — Product Requirements Document

*For use as a build spec with Claude Code*
*February 2025*

---

## 0. What This Is

ContextHub is a tool that lets you **push** LLM conversations from Claude to a central store, **browse** them in a dashboard, and **pull** structured context back into new LLM sessions. Think of it as a personal git repo for your AI conversations.

**This is a solo-user MVP.** No auth, no teams, no invites. One user (hardcoded), one repo of conversations. The goal is to validate whether the push→pull loop is useful before building anything else.

---

## 1. Architecture Overview

```
┌──────────────────┐       ┌──────────────────┐       ┌──────────────────┐
│                  │       │                  │       │                  │
│  Chrome          │──────▶│  Backend API     │──────▶│  SQLite          │
│  Extension       │  POST │  (FastAPI)       │       │  (local DB)      │
│                  │       │                  │       │                  │
└──────────────────┘       └───────┬──────────┘       └──────────────────┘
                                   │
                          ┌────────┴────────┐
                          │                 │
                          ▼                 ▼
                   ┌─────────────┐   ┌─────────────┐
                   │ Claude API  │   │ Web          │
                   │ (extraction)│   │ Dashboard    │
                   │             │   │ (React)      │
                   └─────────────┘   └─────────────┘
```

### Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| Extension | Chrome Extension (Manifest V3) | Required for DOM access |
| Backend | Python + FastAPI | Fast to build, good Anthropic SDK |
| Database | SQLite (single file) | No setup, good enough for solo MVP |
| Extraction | Anthropic API (Claude Sonnet 4.5) | Best extraction quality per dollar |
| Dashboard | React + Vite + Tailwind CSS | Fast to build, good DX |
| Raw storage | Local filesystem (JSON files) | No S3 needed for MVP |

**No external services required except the Anthropic API.** Everything runs locally or on a single server.

---

## 2. Component 1: Chrome Extension (Push)

### 2.1 Purpose

The extension does two things:
1. **Push**: Scrape the current Claude conversation from the DOM and send it to the backend
2. **Pull**: Show recent contexts and copy formatted context to clipboard

### 2.2 File Structure

```
extension/
├── manifest.json
├── background.js            # Service worker — handles backend API calls
├── content-scripts/
│   └── claude.js            # Content script that scrapes conversations from claude.ai
├── popup/
│   ├── popup.html           # Extension popup UI
│   ├── popup.js             # Popup logic
│   └── popup.css            # Popup styles
└── icons/
    ├── icon16.png
    ├── icon48.png
    └── icon128.png
```

### 2.3 manifest.json

```json
{
  "manifest_version": 3,
  "name": "ContextHub",
  "version": "0.1.0",
  "description": "Push and pull context from your Claude conversations",
  "permissions": ["activeTab", "storage", "clipboardWrite"],
  "host_permissions": [
    "https://claude.ai/*"
  ],
  "background": {
    "service_worker": "background.js"
  },
  "content_scripts": [
    {
      "matches": ["https://claude.ai/*"],
      "js": ["content-scripts/claude.js"]
    }
  ],
  "action": {
    "default_popup": "popup/popup.html",
    "default_icon": {
      "16": "icons/icon16.png",
      "48": "icons/icon48.png",
      "128": "icons/icon128.png"
    }
  }
}
```

### 2.4 Content Script: DOM Scraping — claude.ai

The content script scrapes all messages from the current Claude conversation. It runs on every claude.ai page and listens for a message from the popup to trigger scraping.

**What to extract:**
- Every message in the conversation (both user and assistant)
- The role of each message ("user" or "assistant")
- The text content of each message
- The current page URL

**Implementation:**

```javascript
// content-scripts/claude.js

function scrapeConversation() {
  const url = window.location.href;
  
  // Check we're on a conversation page
  if (!url.includes("/chat/")) {
    return { error: "Not on a conversation page", url };
  }

  const messages = [];

  // ============================================================
  // DOM SELECTOR STRATEGY
  // ============================================================
  // Claude.ai's DOM structure changes periodically.
  // The developer MUST inspect the live DOM before building and
  // update these selectors to match the current structure.
  //
  // How to find the right selectors:
  // 1. Open claude.ai, start or load a conversation
  // 2. Right-click on a USER message → Inspect
  // 3. Right-click on an ASSISTANT message → Inspect
  // 4. Find the common container for each message
  // 5. Find what distinguishes user vs assistant messages
  //    (data attributes, class names, nesting structure)
  //
  // Common patterns to look for:
  // - data-testid attributes containing "message" or "turn"
  // - Class names containing "human", "user", "assistant", "claude"
  // - Structural patterns: user messages and assistant messages
  //   typically alternate and have different parent containers
  //   or wrapper elements
  //
  // The selectors below are EXAMPLES — replace with actual ones.
  // ============================================================

  // STRATEGY 1: Try data-testid attributes
  let messageElements = document.querySelectorAll('[data-testid*="message"]');
  
  // STRATEGY 2: If that finds nothing, try common class patterns
  if (messageElements.length === 0) {
    // Try looking for the chat container and its direct message children
    // Claude often wraps each turn in a div with role-specific styling
    messageElements = document.querySelectorAll('[class*="Message"], [class*="message"]');
  }

  // STRATEGY 3: If still nothing, try finding the main chat scroll container
  // and iterating its children. Each child typically represents one turn.
  if (messageElements.length === 0) {
    // Look for the main conversation area
    const chatContainer = document.querySelector('main [class*="chat"], main [class*="conversation"]');
    if (chatContainer) {
      messageElements = chatContainer.children;
    }
  }

  // Extract messages
  for (const el of messageElements) {
    // Determine role based on DOM clues
    let role = null;

    // Check data attributes
    const testId = el.getAttribute("data-testid") || "";
    if (testId.includes("human") || testId.includes("user")) {
      role = "user";
    } else if (testId.includes("assistant") || testId.includes("claude")) {
      role = "assistant";
    }

    // Check class names if data attributes didn't work
    if (!role) {
      const classes = el.className || "";
      if (classes.includes("human") || classes.includes("user")) {
        role = "user";
      } else if (classes.includes("assistant") || classes.includes("claude")) {
        role = "assistant";
      }
    }

    // Skip if we couldn't determine the role (might be a system element)
    if (!role) continue;

    // Extract text content
    // innerText preserves line breaks and strips hidden elements
    const content = el.innerText.trim();

    // Skip empty messages
    if (!content) continue;

    messages.push({ role, content });
  }

  return {
    source: "claude",
    url: url,
    scraped_at: new Date().toISOString(),
    messages: messages
  };
}

// Listen for scrape requests from the popup
chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  if (request.action === "scrape") {
    const result = scrapeConversation();
    sendResponse(result);
  }
  return true; // Keep channel open for async
});
```

**CRITICAL — DEVELOPER MUST DO BEFORE ANYTHING ELSE:**
1. Open claude.ai in Chrome
2. Open DevTools → Elements tab
3. Load a conversation with several back-and-forth messages
4. Inspect a user message and an assistant message
5. Find the actual selectors that work — class names, data attributes, DOM structure
6. Update the selector strategies in the code above
7. Test that scraping returns all messages with correct roles

**Known edge cases to handle:**
- Empty conversations (no messages yet) → return empty array, popup shows "No messages found"
- Code blocks → `innerText` handles these fine, preserves the text content
- Very long conversations → all messages should be in the DOM unless Claude uses virtual scrolling (unlikely for typical conversation lengths, but test with a 50+ message conversation)
- Images/file uploads in messages → `innerText` will skip these, which is fine for MVP
- Thinking/artifacts sections → these may appear as extra elements; the role detection should skip them if they don't match "user" or "assistant"

### 2.5 Background Script

The background service worker handles communication between the popup, content script, and ContextHub backend.

```javascript
// background.js

const API_BASE = "http://localhost:8000";

chrome.runtime.onMessage.addListener((request, sender, sendResponse) => {
  
  if (request.action === "push") {
    // request.data = scraped conversation from content script
    fetch(`${API_BASE}/api/threads`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(request.data)
    })
    .then(res => {
      if (!res.ok) throw new Error(`Server error: ${res.status}`);
      return res.json();
    })
    .then(data => sendResponse({ success: true, thread: data }))
    .catch(err => sendResponse({ success: false, error: err.message }));
    return true; // Async response
  }
  
  if (request.action === "get_recent") {
    fetch(`${API_BASE}/api/threads?limit=5`)
    .then(res => res.json())
    .then(data => sendResponse({ success: true, threads: data }))
    .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }
  
  if (request.action === "get_thread") {
    fetch(`${API_BASE}/api/threads/${request.thread_id}`)
    .then(res => res.json())
    .then(data => sendResponse({ success: true, thread: data }))
    .catch(err => sendResponse({ success: false, error: err.message }));
    return true;
  }
});
```

### 2.6 Extension Popup — UI Spec

The popup has two views: **Push** and **Pull**.

**Default view (Push + recent contexts):**

```
┌────────────────────────────────────┐
│  ContextHub                    ⚙️  │
├────────────────────────────────────┤
│                                    │
│  ┌──────────────────────────────┐  │
│  │  📤 Push This Conversation  │  │
│  └──────────────────────────────┘  │
│                                    │
│  ─────── Recent Contexts ───────  │
│                                    │
│  📝 Auth System Architecture      │
│     2 hours ago • claude           │
│     [Copy Context]                 │
│                                    │
│  📝 Pricing Strategy               │
│     Yesterday • claude             │
│     [Copy Context]                 │
│                                    │
│  📝 Database Schema Design         │
│     2 days ago • claude            │
│     [Copy Context]                 │
│                                    │
│  ──────────────────────────────── │
│  [Open Dashboard ↗]               │
│                                    │
└────────────────────────────────────┘
```

**Popup dimensions:** 380px wide × 500px tall (max)

**Push button behavior:**
1. User clicks "Push This Conversation"
2. Button changes to "Pushing..." with a spinner
3. Popup sends `scrape` message to content script on the active tab
4. Content script scrapes the conversation from the DOM and returns it
5. Popup sends `push` message to background script with the scraped data
6. Background script POSTs the data to ContextHub backend
6. On success: button shows "✓ Pushed!" for 2 seconds, then reverts
7. On error: button shows "✗ Failed — try again" in red

**Recent contexts list:**
- Shows the 5 most recent pushed contexts (fetched from backend on popup open)
- Each item shows: title, relative time (e.g., "2 hours ago"), source label
- "Copy Context" button on each item — copies formatted context block to clipboard
- Clicking the title opens the full context in the dashboard (new tab)

**Copy Context behavior:**
1. User clicks "Copy Context" on a context item
2. Extension fetches the full context from the backend
3. Formats it as a context block (see Pull format below in Section 4.5)
4. Copies to clipboard
5. Button briefly shows "✓ Copied!"

**"Open Dashboard" link:**
- Opens the web dashboard in a new tab
- URL: `http://localhost:3000` (for MVP)

---

## 3. Component 2: Backend API

### 3.1 Purpose

The backend receives raw conversations, runs extraction via Claude API, stores everything, and serves data to the extension and dashboard.

### 3.2 Project Structure

```
backend/
├── main.py                 # FastAPI app + routes
├── extraction.py           # Claude API extraction logic
├── models.py               # SQLAlchemy models
├── database.py             # DB setup + session
├── requirements.txt
├── raw_transcripts/        # Raw JSON files stored here
└── .env                    # ANTHROPIC_API_KEY
```

### 3.3 Database Schema (SQLite)

```sql
CREATE TABLE threads (
  id TEXT PRIMARY KEY,           -- UUID as string
  source TEXT NOT NULL DEFAULT 'claude',  -- "claude" (extensible to other platforms later)
  source_url TEXT,               -- Original conversation URL
  
  -- Extracted content (filled async after push)
  title TEXT,
  summary TEXT,
  decisions TEXT,                -- JSON array of strings
  artifacts TEXT,                -- JSON array of {type, language, content}
  open_questions TEXT,           -- JSON array of strings
  entities TEXT,                 -- JSON array of strings
  
  -- Metadata
  raw_transcript_path TEXT,      -- Path to raw JSON file
  extraction_status TEXT DEFAULT 'pending',  -- "pending" | "processing" | "done" | "failed"
  message_count INTEGER,         -- Number of messages in conversation
  
  created_at TEXT DEFAULT (datetime('now')),
  updated_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE pull_events (
  id TEXT PRIMARY KEY,
  thread_id TEXT REFERENCES threads(id),
  pulled_at TEXT DEFAULT (datetime('now'))
);
```

### 3.4 API Endpoints

#### `POST /api/threads`

Receives a raw conversation, stores it, kicks off extraction.

**Request body:**
```json
{
  "source": "claude",
  "url": "https://claude.ai/chat/abc123",
  "scraped_at": "2025-02-05T10:30:00Z",
  "messages": [
    {"role": "user", "content": "Help me design an auth system..."},
    {"role": "assistant", "content": "Sure! Let's think about this..."},
    {"role": "user", "content": "What about JWT vs sessions?"},
    {"role": "assistant", "content": "Great question. Here's the tradeoff..."}
  ]
}
```

**What the endpoint does:**
1. Generate a UUID for the thread
2. Save the raw conversation as a JSON file to `raw_transcripts/{id}.json`
3. Create a thread record in SQLite with `extraction_status = "pending"`
4. **Synchronously** call the extraction function (for MVP simplicity — async is overkill for one user)
5. Update the thread record with extracted fields + `extraction_status = "done"`
6. If extraction fails, set `extraction_status = "failed"` and store the error
7. Return the full thread object

**Response (201 Created):**
```json
{
  "id": "550e8400-e29b-41d4-a716-446655440000",
  "source": "claude",
  "source_url": "https://claude.ai/chat/abc123",
  "title": "Auth System Architecture Design",
  "summary": "Explored authentication approaches for a web app. Decided on JWT with refresh tokens over session-based auth for scalability.",
  "decisions": [
    "Use JWT over session-based auth (stateless, scales better)",
    "15-minute access token, 7-day refresh token",
    "Store refresh tokens in httpOnly cookies"
  ],
  "artifacts": [
    {
      "type": "code",
      "language": "javascript",
      "content": "const generateTokens = (userId) => { ... }"
    }
  ],
  "open_questions": [
    "How to handle token revocation at scale?",
    "Rate limiting strategy for auth endpoints?"
  ],
  "entities": ["JWT", "authentication", "refresh tokens", "security"],
  "extraction_status": "done",
  "message_count": 4,
  "created_at": "2025-02-05T10:30:00Z"
}
```

#### `GET /api/threads`

List all threads, most recent first.

**Query params:**
- `limit` (int, default 20, max 100) — number of threads to return
- `offset` (int, default 0) — pagination offset

**Response (200):**
```json
{
  "threads": [
    {
      "id": "550e8400-...",
      "source": "claude",
      "title": "Auth System Architecture Design",
      "summary": "Explored authentication approaches...",
      "decisions": ["Use JWT over session-based auth..."],
      "open_questions": ["How to handle token revocation..."],
      "entities": ["JWT", "authentication"],
      "extraction_status": "done",
      "message_count": 4,
      "created_at": "2025-02-05T10:30:00Z"
    }
  ],
  "total": 42,
  "limit": 20,
  "offset": 0
}
```

**Note:** The list endpoint returns the full extracted content for each thread (not a truncated version). At MVP scale (dozens of threads, not thousands), this is fine.

#### `GET /api/threads/{thread_id}`

Get a single thread with all details.

**Response (200):** Same shape as a single thread object above, plus:
```json
{
  ...all thread fields,
  "raw_transcript_path": "raw_transcripts/550e8400-....json"
}
```

**Response (404):** `{"detail": "Thread not found"}`

#### `GET /api/threads/{thread_id}/raw`

Returns the raw transcript JSON file for a thread. This is for the "View Raw Transcript" feature in the dashboard.

**Response (200):** The raw JSON content of the stored transcript file.

#### `GET /api/threads/{thread_id}/context`

Returns the formatted context block ready to paste into a new LLM session.

**Response (200):**
```json
{
  "formatted_context": "[Context from ContextHub]\nPreviously, we discussed Auth System Architecture Design:\n\nSummary: Explored authentication approaches...\n\nKey decisions:\n- Use JWT over session-based auth...\n- 15-minute access token, 7-day refresh token\n\nOpen questions:\n- How to handle token revocation at scale?\n[End Context]"
}
```

#### `POST /api/threads/{thread_id}/pull`

Record a pull event (for analytics).

**Response (201):** `{"id": "...", "thread_id": "...", "pulled_at": "..."}`

#### `GET /api/stats`

Basic usage stats for the dashboard.

**Response (200):**
```json
{
  "total_threads": 42,
  "total_pulls": 18,
  "threads_this_week": 7,
  "pulls_this_week": 5
}
```

### 3.5 Extraction Logic

This is the core value engine of the product.

**File: `extraction.py`**

```python
import anthropic
import json

EXTRACTION_PROMPT = """You are an expert at extracting structured knowledge from conversations between a user and an AI assistant.

Given the following conversation, extract structured information that would be useful for someone (including the original user) to quickly understand what was discussed and decided.

Extract the following:

1. TITLE: A descriptive title (5-10 words) that captures the main topic. Should be specific enough to distinguish from other conversations. Bad: "Coding Help". Good: "Auth System Architecture with JWT Tokens".

2. SUMMARY: 2-3 sentences capturing the key outcome, insight, or conclusion. Write this as if briefing a teammate who needs to get up to speed quickly. Focus on what was decided or concluded, not what was discussed.

3. DECISIONS: An array of explicit decisions that were made during the conversation. Only include things that were actually decided, not options that were merely considered. Each decision should be one clear sentence. If no decisions were made, return an empty array.

4. ARTIFACTS: An array of concrete outputs produced — code snippets, configurations, structured data, templates, etc. Each artifact should have:
   - "type": one of "code", "config", "template", "data", "other"
   - "language": programming language if applicable (e.g., "python", "javascript", "sql"), otherwise null
   - "description": one-line description of what this artifact is
   - "content": the full content of the artifact
   Only include substantial artifacts (not one-liners mentioned in passing). If no artifacts, return an empty array.

5. OPEN_QUESTIONS: An array of unresolved questions, items flagged for follow-up, or next steps that were mentioned but not completed. Each should be a clear, actionable question or task. If none, return empty array.

6. ENTITIES: An array of key topics, technologies, projects, or concepts that were central to the conversation. These serve as tags for finding this context later. 5-10 items max.

CRITICAL GUIDELINES:
- Be concise. This output will be pasted into future LLM sessions as context, so every word should earn its place.
- Prioritize decisions and outcomes over process. The user was there — they don't need a play-by-play.
- For artifacts, include the FULL content, not a truncated version. Code should be complete and runnable.
- Write the summary in a way that would make sense to a teammate who wasn't part of the conversation.
- If the conversation is exploratory with no clear decisions, that's fine — say so in the summary and focus on key insights.

Return ONLY valid JSON with this exact structure (no markdown, no explanation, no preamble):
{
  "title": "string",
  "summary": "string",
  "decisions": ["string"],
  "artifacts": [{"type": "string", "language": "string|null", "description": "string", "content": "string"}],
  "open_questions": ["string"],
  "entities": ["string"]
}"""

def extract_context(messages: list[dict]) -> dict:
    """
    Takes a list of messages [{role, content}] and returns extracted context.
    """
    # Format the conversation for the prompt
    conversation_text = ""
    for msg in messages:
        role_label = "User" if msg["role"] == "user" else "Assistant"
        conversation_text += f"\n{role_label}: {msg['content']}\n"
    
    client = anthropic.Anthropic()  # Uses ANTHROPIC_API_KEY env var
    
    response = client.messages.create(
        model="claude-sonnet-4-5-20250514",
        max_tokens=4096,
        messages=[
            {
                "role": "user", 
                "content": f"{EXTRACTION_PROMPT}\n\nCONVERSATION:\n---\n{conversation_text}\n---"
            }
        ]
    )
    
    # Parse the response
    raw_text = response.content[0].text
    
    # Clean up potential markdown formatting
    if raw_text.startswith("```"):
        raw_text = raw_text.split("\n", 1)[1]  # Remove first line
        raw_text = raw_text.rsplit("```", 1)[0]  # Remove last ```
    
    extracted = json.loads(raw_text)
    
    # Validate required fields
    required = ["title", "summary", "decisions", "artifacts", "open_questions", "entities"]
    for field in required:
        if field not in extracted:
            extracted[field] = [] if field != "title" and field != "summary" else ""
    
    return extracted
```

**Handling long conversations:**
- If a conversation exceeds ~150K tokens (unlikely for MVP but possible), truncate from the middle — keep the first 20% and last 50% of messages, as the end usually has conclusions.
- For MVP, just send the full conversation and let the API handle it. Claude Sonnet has a 200K context window.

**Handling extraction failures:**
- If the Claude API call fails (rate limit, server error), set `extraction_status = "failed"` on the thread
- Store the error message
- The dashboard should show "Extraction failed — click to retry" on these threads
- Provide a `POST /api/threads/{thread_id}/retry` endpoint that re-runs extraction

### 3.6 CORS Configuration

The backend must allow requests from:
- The Chrome extension (origin will be `chrome-extension://<extension-id>`)
- The dashboard (`http://localhost:3000`)

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # For MVP, allow all origins. Lock down later.
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

### 3.7 Running the Backend

```bash
# Install dependencies
pip install fastapi uvicorn anthropic sqlalchemy python-dotenv

# Set up environment
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# Run
uvicorn main:app --reload --port 8000
```

---

## 4. Component 3: Web Dashboard

### 4.1 Purpose

A simple web app where the user can browse all pushed contexts, search them, view details, and copy formatted context for pulling into new sessions.

### 4.2 Project Structure

```
dashboard/
├── src/
│   ├── App.jsx
│   ├── main.jsx
│   ├── index.css              # Tailwind imports
│   ├── api.js                 # API client
│   ├── components/
│   │   ├── ThreadList.jsx     # Main list view
│   │   ├── ThreadCard.jsx     # Individual thread card
│   │   ├── ThreadDetail.jsx   # Full thread view
│   │   ├── SearchBar.jsx      # Search input
│   │   ├── Stats.jsx          # Usage stats bar
│   │   └── CopyButton.jsx    # Reusable copy-to-clipboard button
│   └── utils/
│       ├── formatContext.js   # Format thread into pasteable context block
│       └── timeAgo.js         # Relative time formatting
├── index.html
├── package.json
├── vite.config.js
├── tailwind.config.js
└── postcss.config.js
```

### 4.3 Page: Thread List (Home — `/`)

This is the main view. A reverse-chronological feed of all pushed contexts.

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ContextHub                                              [Stats ▼] │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │ 🔍  Search your contexts...                                  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Auth System Architecture Design                              │  │
│  │  2 hours ago                                                  │  │
│  │                                                               │  │
│  │  Explored authentication approaches for a web app.            │  │
│  │  Decided on JWT with refresh tokens over session-based        │  │
│  │  auth for scalability.                                        │  │
│  │                                                               │  │
│  │  Decisions:                                                   │  │
│  │  • Use JWT over session-based auth                            │  │
│  │  • 15-minute access token, 7-day refresh token                │  │
│  │                                                               │  │
│  │  Open: How to handle token revocation at scale?               │  │
│  │                                                               │  │
│  │  jwt · authentication · security                              │  │
│  │                                                               │  │
│  │  [Copy Context]                                     [View →]  │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────────────────────────────────────────────────────┐  │
│  │  Pricing Strategy Exploration                                 │  │
│  │  Yesterday                                                    │  │
│  │  ...                                                          │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Thread card displays:**
- Title (bold, clickable — navigates to detail view)
- Source indicator (🟣 for Claude) + source name
- Relative time ("2 hours ago", "Yesterday", "3 days ago")
- Summary text (full, not truncated)
- First 2-3 decisions (if any)
- First open question (if any), prefixed with "Open:"
- Entity tags (as small pills/badges)
- "Copy Context" button — copies formatted context block to clipboard
- "View →" link — navigates to detail page

**Search:**
- Simple client-side text search for MVP
- Searches across title, summary, decisions, open_questions, and entities
- Filters the list in real-time as the user types
- No debounce needed at MVP scale

**Stats bar (collapsible):**
- Total contexts pushed
- Contexts this week
- Total pulls

### 4.4 Page: Thread Detail (`/thread/:id`)

Full view of a single pushed context.

```
┌─────────────────────────────────────────────────────────────────────┐
│                                                                     │
│  ← Back                                          [Copy Context]    │
│                                                                     │
│  Auth System Architecture Design                                    │
│  Pushed 2 hours ago • Source: Claude • 24 messages                 │
│  Original: claude.ai/chat/abc123                                    │
│                                                                     │
│  ┌───────────────── SUMMARY ────────────────────────────────────┐  │
│  │                                                               │  │
│  │  Explored authentication approaches for a web app. Decided    │  │
│  │  on JWT with refresh tokens over session-based auth for       │  │
│  │  scalability. Also discussed token storage strategies and     │  │
│  │  refresh token rotation.                                      │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────── DECISIONS ──────────────────────────────────┐  │
│  │                                                               │  │
│  │  ✓ Use JWT over session-based auth (stateless, scales better)│  │
│  │  ✓ 15-minute access token, 7-day refresh token               │  │
│  │  ✓ Store refresh tokens in httpOnly cookies                  │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────── ARTIFACTS ──────────────────────────────────┐  │
│  │                                                               │  │
│  │  Token generation utility (JavaScript)                       │  │
│  │  ┌─────────────────────────────────────────────────────┐     │  │
│  │  │ const generateTokens = (userId) => {                │     │  │
│  │  │   const accessToken = jwt.sign(                     │     │  │
│  │  │     { userId },                                     │     │  │
│  │  │     process.env.ACCESS_SECRET,                      │     │  │
│  │  │     { expiresIn: '15m' }                            │     │  │
│  │  │   );                                                │     │  │
│  │  │   ...                                               │     │  │
│  │  │ };                                                  │     │  │
│  │  └─────────────────────────────────────────────── [Copy]     │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────── OPEN QUESTIONS ─────────────────────────────┐  │
│  │                                                               │  │
│  │  ? How to handle token revocation at scale?                  │  │
│  │  ? Rate limiting strategy for auth endpoints?                │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  ┌───────────────── ENTITIES ───────────────────────────────────┐  │
│  │                                                               │  │
│  │  [JWT] [authentication] [refresh tokens] [security]          │  │
│  │                                                               │  │
│  └───────────────────────────────────────────────────────────────┘  │
│                                                                     │
│  [View Raw Transcript ↓]                                           │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

**Detail page features:**
- Back button → returns to list
- "Copy Context" button (top right) — copies the formatted context block
- All extracted sections displayed in clear, labeled cards
- Artifacts shown in code blocks with syntax highlighting (use a simple `<pre><code>` for MVP, or a lightweight library like `highlight.js`)
- "View Raw Transcript" — collapsible section at the bottom showing the raw conversation messages. Each message displayed with role label and content. This is a secondary feature, collapsed by default.
- Link to original conversation URL (opens in new tab)

### 4.5 Pull Context Format

When the user clicks "Copy Context" (either in the dashboard or extension popup), this is the exact text that gets copied to their clipboard:

```
[Context from ContextHub]
Previously, I discussed: {title}

Summary: {summary}

{if decisions.length > 0}
Key decisions:
{for each decision}
- {decision}
{end for}
{end if}

{if open_questions.length > 0}
Open questions:
{for each question}
- {question}
{end for}
{end if}

{if artifacts.length > 0}
Artifacts produced:
{for each artifact}
[{artifact.description}]
```{artifact.language}
{artifact.content}
```
{end for}
{end if}
[End Context]
```

**Implementation (JavaScript):**

```javascript
// utils/formatContext.js

export function formatContext(thread) {
  let output = `[Context from ContextHub]\n`;
  output += `Previously, I discussed: ${thread.title}\n\n`;
  output += `Summary: ${thread.summary}\n`;
  
  if (thread.decisions && thread.decisions.length > 0) {
    output += `\nKey decisions:\n`;
    thread.decisions.forEach(d => { output += `- ${d}\n`; });
  }
  
  if (thread.open_questions && thread.open_questions.length > 0) {
    output += `\nOpen questions:\n`;
    thread.open_questions.forEach(q => { output += `- ${q}\n`; });
  }
  
  if (thread.artifacts && thread.artifacts.length > 0) {
    output += `\nArtifacts produced:\n`;
    thread.artifacts.forEach(a => {
      output += `[${a.description}]\n`;
      output += `\`\`\`${a.language || ''}\n${a.content}\n\`\`\`\n`;
    });
  }
  
  output += `[End Context]`;
  return output;
}
```

### 4.6 Design Guidelines

**Visual style:**
- Clean, minimal, monochrome with subtle accent colors
- White background, dark text
- Cards with light borders (gray-200) and slight rounded corners
- Source indicator: 🟣 purple dot for Claude conversations
- Entity tags: small rounded pills with light background (gray-100)
- Use system fonts (no custom fonts for MVP)

**Tailwind classes to use heavily:**
- `bg-white`, `border`, `border-gray-200`, `rounded-lg`, `shadow-sm`
- `text-gray-900` for primary text, `text-gray-500` for secondary
- `p-4`, `p-6` for card padding
- `space-y-4` for vertical spacing between cards
- `max-w-3xl mx-auto` for content width (keep it narrow and readable)

**Responsive:** Not required for MVP. Design for desktop only (1024px+ viewport).

---

## 5. Error Handling

### Extension Errors

| Error | User sees | Behavior |
|-------|-----------|----------|
| No conversation found on page | "No conversation detected on this page." | Disable push button |
| Backend unreachable | "Can't reach ContextHub. Is the server running?" | Show in popup |
| Push fails (server error) | "Push failed — try again" | Button turns red, resets after 3s |
| Scraping returns empty | "No messages found. Try refreshing the page." | Disable push button |

### Backend Errors

| Error | HTTP Status | Response |
|-------|-------------|----------|
| Invalid request body | 400 | `{"detail": "Missing required field: messages"}` |
| Thread not found | 404 | `{"detail": "Thread not found"}` |
| Extraction fails | 201 (still save) | Thread saved with `extraction_status: "failed"` |
| Anthropic API error | 201 (still save) | Same — save thread, mark extraction failed |

### Dashboard Errors

| Error | User sees |
|-------|-----------|
| Backend unreachable | "Can't connect to server. Make sure the backend is running on port 8000." |
| Thread load fails | "Failed to load this context." with retry button |
| Clipboard copy fails | "Couldn't copy — please try again" |

---

## 6. Development Setup & Running

### Prerequisites

- Python 3.11+
- Node.js 18+
- Chrome browser
- Anthropic API key

### Quick Start

```bash
# 1. Backend
cd backend
pip install -r requirements.txt
echo "ANTHROPIC_API_KEY=sk-ant-your-key-here" > .env
uvicorn main:app --reload --port 8000

# 2. Dashboard  
cd dashboard
npm install
npm run dev
# Runs on http://localhost:3000

# 3. Extension
# Open chrome://extensions
# Enable Developer Mode
# Click "Load unpacked" → select the extension/ folder
# Pin the ContextHub extension
```

### Testing the Full Flow

1. Open claude.ai, have a conversation
2. Click the ContextHub extension icon
3. Click "Push This Conversation"
4. Open http://localhost:3000 — you should see the extracted context
5. Click "Copy Context" on the card
6. Open a new Claude conversation, paste the context
7. Verify the context is useful

---

## 7. What Is Explicitly NOT in V1

These are intentionally excluded to keep scope tight:

| Feature | Why excluded |
|---------|-------------|
| User authentication | Solo user, no need |
| Team creation / invites | Validate solo loop first |
| Projects / tags / organization | Keep it flat and messy |
| Semantic search | Keyword search is enough for <100 threads |
| ChatGPT / Gemini support | Claude only for MVP — add other platforms after validating the loop |
| Auto-detection of "valuable" conversations | Manual push is fine for validation |
| Auto-injection of context into LLM sessions | Copy-paste is fine for MVP |
| Edit/delete functionality for threads | Not needed for validation |
| Mobile support | Desktop only |
| Deployment / hosting | Everything runs locally |
| Slack/Notion integrations | Scope creep |
| SSO / OAuth | No auth at all for MVP |

---

## 8. File Deliverables

When complete, the repo should look like:

```
contexthub/
├── extension/
│   ├── manifest.json
│   ├── background.js            # Service worker — handles backend communication
│   ├── content-scripts/
│   │   └── claude.js            # Scrapes conversation from claude.ai DOM
│   ├── popup/
│   │   ├── popup.html
│   │   ├── popup.js
│   │   └── popup.css
│   └── icons/
│       └── (placeholder icons)
├── backend/
│   ├── main.py
│   ├── extraction.py
│   ├── models.py
│   ├── database.py
│   ├── requirements.txt
│   └── .env.example
├── dashboard/
│   ├── src/
│   │   ├── App.jsx
│   │   ├── main.jsx
│   │   ├── index.css
│   │   ├── api.js
│   │   ├── components/
│   │   │   ├── ThreadList.jsx
│   │   │   ├── ThreadCard.jsx
│   │   │   ├── ThreadDetail.jsx
│   │   │   ├── SearchBar.jsx
│   │   │   ├── Stats.jsx
│   │   │   └── CopyButton.jsx
│   │   └── utils/
│   │       ├── formatContext.js
│   │       └── timeAgo.js
│   ├── index.html
│   ├── package.json
│   ├── vite.config.js
│   ├── tailwind.config.js
│   └── postcss.config.js
└── README.md                    # Setup instructions
```

---

## 9. Success Criteria for This Build

The build is done when:

- [ ] Extension can scrape a conversation from claude.ai
- [ ] Clicking "Push" sends the conversation to the backend
- [ ] Backend saves the raw transcript and runs extraction
- [ ] Extraction produces title, summary, decisions, artifacts, open_questions, entities
- [ ] Dashboard shows a list of all pushed threads
- [ ] Dashboard has working search (filters threads by text)
- [ ] Clicking a thread shows the full detail view
- [ ] "Copy Context" copies a formatted context block to clipboard
- [ ] The extension popup shows 5 recent contexts with copy buttons
- [ ] The full push → browse → pull loop works end to end
