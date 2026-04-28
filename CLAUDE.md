# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

ContextHub captures Claude conversations, extracts structured context via the Claude API, and lets you copy formatted context into new conversations. Three components: backend API, React dashboard, Chrome extension.

## Commands

### Backend (Python/FastAPI)
```bash
cd backend && source venv/bin/activate

# Run server (port 8001)
uvicorn main:app --reload --port 8001

# Run all backend tests
python -m pytest test_backend.py -v

# Run a single test
python -m pytest test_backend.py::test_create_thread_success -v

# Run extension structural tests (uses backend venv)
python -m pytest ../extension/test_extension.py -v
```

### Dashboard (React/Vite)
```bash
cd dashboard

# Dev server (port 3000)
npm run dev

# Run all dashboard tests
npm test

# Run a specific test file
npx vitest run src/__tests__/formatContext.test.js

# Lint
npm run lint

# Production build
npm run build
```

### Chrome Extension
Load unpacked from `extension/` directory in `chrome://extensions` with Developer Mode enabled.

## Architecture

**Push flow:** Chrome extension scrapes claude.ai DOM → POSTs messages to `POST /api/threads` → backend saves raw transcript to `data/transcripts/{id}.json` → calls Claude Sonnet 4.5 for extraction → stores structured data in SQLite.

**Pull flow:** Dashboard fetches thread list → user clicks "Copy Context" → `GET /api/threads/{id}/context?format=summary|full` → formatted text block copied to clipboard → paste into new Claude conversation.

### Backend (`backend/`)
- `main.py` — FastAPI app with all REST endpoints. CORS allows all origins.
- `extraction.py` — LLM extraction pipeline. Sends conversation to Claude Sonnet 4.5 with structured prompt. Returns: title, conversation_type, summary, key_takeaways, artifacts, open_threads, tags. Has `extract_context_mock()` fallback when no API key.
- `models.py` — SQLAlchemy models: `Thread` (JSON fields stored as TEXT, deserialized in `to_dict()`), `PullEvent`.
- `database.py` — SQLite engine, session factory, `get_db()` dependency.

### Dashboard (`dashboard/`)
- Tailwind CSS v4 via `@tailwindcss/vite` plugin (NOT config files). CSS uses `@import "tailwindcss"`.
- `src/api.js` — all fetch calls to `http://localhost:8001`.
- Routes: `/` → `ThreadList`, `/thread/:id` → `ThreadDetail`.
- `src/utils/formatContext.js` — formats thread into clipboard-ready context block with smart artifact handling (≤3 inline, >3 shows count note).

### Extension (`extension/`)
- Manifest V3. Content script on `claude.ai` with 3 fallback DOM scraping strategies.
- `background.js` — service worker handling `push`, `get_recent`, `get_thread`, `get_context` messages.
- `popup/popup.js` — push button, recent contexts list, copy-to-clipboard.

## Key Patterns

- **JSON-as-TEXT columns**: `key_takeaways`, `artifacts`, `open_threads`, `tags` are stored as JSON strings in SQLite, deserialized in `Thread.to_dict()`.
- **Extraction status lifecycle**: `pending` → `processing` → `done` | `failed`. Failed extractions can be retried via `POST /api/threads/{id}/retry`.
- **Context formats**: Summary (default) returns compact context block. Full (`?format=full`) includes entire raw transcript.
- **Test isolation**: Backend tests use in-memory SQLite with `StaticPool` to share a single connection. Dashboard tests use `cleanup()` + `vi.restoreAllMocks()` in `afterEach`.

## API Endpoints

```
POST /api/threads          — push conversation (requires messages array)
GET  /api/threads          — list (limit/offset pagination)
GET  /api/threads/{id}     — detail
GET  /api/threads/{id}/raw — raw transcript messages
GET  /api/threads/{id}/context?format=summary|full — formatted pull context
POST /api/threads/{id}/pull   — record pull event
POST /api/threads/{id}/retry  — retry failed extraction
GET  /api/stats            — thread/pull counts (total + this week)
```
