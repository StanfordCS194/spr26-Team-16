# ContextHub

Push LLM conversations to a central store, browse extracted context in a dashboard, and pull formatted context back into new sessions.

## Prerequisites

- Python 3.11+
- Node.js 18+
- Chrome browser
- Anthropic API key

## Quick Start

### 1. Backend

```bash
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# Edit .env and add your Anthropic API key
uvicorn main:app --reload --port 8001
```

### 2. Dashboard

```bash
cd dashboard
npm install
npm run dev
# Runs on http://localhost:3000
```

### 3. Chrome Extension

1. Open `chrome://extensions`
2. Enable Developer Mode
3. Click "Load unpacked" and select the `extension/` folder
4. Pin the ContextHub extension

## Testing the Full Flow

1. Open claude.ai and have a conversation
2. Click the ContextHub extension icon
3. Click "Push This Conversation"
4. Open http://localhost:3000 to see the extracted context
5. Click "Copy Context" on any card
6. Paste into a new Claude conversation

## Running Tests

```bash
# Backend tests
cd backend
source venv/bin/activate
pip install pytest httpx
python -m pytest test_backend.py -v

# Dashboard tests
cd dashboard
npm test

# Extension structural tests
cd backend
source venv/bin/activate
python -m pytest ../extension/test_extension.py -v
```
