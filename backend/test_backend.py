"""
Comprehensive tests for ContextHub backend.
Tests all API endpoints, database operations, extraction logic, and helper functions.
"""

import os
import json
import pytest
from unittest.mock import patch, MagicMock

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from database import Base, get_db
from models import Thread, PullEvent

# --- Test DB setup (in-memory SQLite with shared connection) ---
test_engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestSession = sessionmaker(autocommit=False, autoflush=False, bind=test_engine)

# Import app after DB setup
from main import app


def override_get_db():
    db = TestSession()
    try:
        yield db
    finally:
        db.close()


app.dependency_overrides[get_db] = override_get_db

client = TestClient(app)

SAMPLE_CONVERSATION = {
    "source": "claude",
    "url": "https://claude.ai/chat/test-123",
    "scraped_at": "2025-02-05T10:30:00Z",
    "messages": [
        {"role": "user", "content": "Help me design an auth system using JWT"},
        {
            "role": "assistant",
            "content": "Sure! JWT is great for stateless auth. Here's the approach: use access tokens (15min) and refresh tokens (7 days).",
        },
        {"role": "user", "content": "What about storing refresh tokens?"},
        {
            "role": "assistant",
            "content": "Store them in httpOnly cookies. That's the most secure approach for web apps.",
        },
    ],
}

MOCK_EXTRACTION_RESULT = {
    "title": "Auth System Design with JWT Tokens",
    "conversation_type": "build",
    "summary": "Discussed JWT-based authentication. Decided on short-lived access tokens with refresh token rotation stored in httpOnly cookies.",
    "key_takeaways": [
        "Use JWT for stateless authentication",
        "15-minute access tokens, 7-day refresh tokens",
        "Store refresh tokens in httpOnly cookies",
    ],
    "artifacts": [
        {
            "type": "code",
            "language": "javascript",
            "description": "JWT token generation utility",
            "content": "const jwt = require('jsonwebtoken');\nconst generateTokens = (userId) => ({ access: jwt.sign({userId}, SECRET, {expiresIn: '15m'}) });",
        }
    ],
    "open_threads": ["How to handle token revocation at scale?"],
    "tags": ["JWT", "authentication", "refresh tokens", "security", "cookies"],
}


@pytest.fixture(autouse=True)
def setup_and_teardown():
    """Create fresh tables before each test, drop after."""
    Base.metadata.create_all(bind=test_engine)
    os.makedirs("data/transcripts", exist_ok=True)
    yield
    Base.metadata.drop_all(bind=test_engine)
    # Clean up transcript files created during tests
    transcript_dir = "data/transcripts"
    if os.path.exists(transcript_dir):
        for f in os.listdir(transcript_dir):
            if f.endswith(".json"):
                os.remove(os.path.join(transcript_dir, f))


# ===== POST /api/threads =====


@patch("main.extract_context", return_value=MOCK_EXTRACTION_RESULT)
def test_create_thread_success(mock_extract):
    """POST /api/threads should create a thread and return 201 with extracted data."""
    response = client.post("/api/threads", json=SAMPLE_CONVERSATION)
    assert response.status_code == 201
    data = response.json()

    assert "id" in data
    assert data["source"] == "claude"
    assert data["source_url"] == "https://claude.ai/chat/test-123"
    assert data["title"] == "Auth System Design with JWT Tokens"
    assert data["conversation_type"] == "build"
    assert data["extraction_status"] == "done"
    assert data["message_count"] == 4
    assert len(data["key_takeaways"]) == 3
    assert len(data["artifacts"]) == 1
    assert len(data["tags"]) == 5
    assert len(data["open_threads"]) == 1
    assert data["created_at"] is not None

    # Verify raw transcript was saved
    raw_path = f"data/transcripts/{data['id']}.json"
    assert os.path.exists(raw_path)
    with open(raw_path) as f:
        raw = json.load(f)
    assert raw == SAMPLE_CONVERSATION["messages"]

    mock_extract.assert_called_once()


def test_create_thread_missing_messages():
    """POST /api/threads without messages should return 400."""
    response = client.post("/api/threads", json={"source": "claude"})
    assert response.status_code == 400
    assert "messages" in response.json()["detail"]


def test_create_thread_empty_messages():
    """POST /api/threads with empty messages array should return 400."""
    response = client.post("/api/threads", json={"messages": []})
    assert response.status_code == 400


@patch(
    "main.extract_context",
    side_effect=Exception("Anthropic API rate limited"),
)
def test_create_thread_extraction_failure(mock_extract):
    """POST /api/threads should still return 201 even if extraction fails."""
    response = client.post("/api/threads", json=SAMPLE_CONVERSATION)
    assert response.status_code == 201
    data = response.json()

    assert data["extraction_status"] == "failed"
    assert "rate limited" in data["extraction_error"]
    assert data["title"] is None
    assert data["message_count"] == 4


@patch("main.extract_context", return_value=MOCK_EXTRACTION_RESULT)
def test_create_thread_default_source(mock_extract):
    """POST /api/threads without source should default to 'claude'."""
    response = client.post(
        "/api/threads",
        json={"messages": [{"role": "user", "content": "hello"}]},
    )
    assert response.status_code == 201
    assert response.json()["source"] == "claude"


# ===== GET /api/threads =====


@patch("main.extract_context", return_value=MOCK_EXTRACTION_RESULT)
def test_list_threads(mock_extract):
    """GET /api/threads should return paginated thread list."""
    for _ in range(3):
        client.post("/api/threads", json=SAMPLE_CONVERSATION)

    response = client.get("/api/threads")
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 3
    assert len(data["threads"]) == 3
    assert data["limit"] == 20
    assert data["offset"] == 0


@patch("main.extract_context", return_value=MOCK_EXTRACTION_RESULT)
def test_list_threads_pagination(mock_extract):
    """GET /api/threads should respect limit and offset."""
    for _ in range(5):
        client.post("/api/threads", json=SAMPLE_CONVERSATION)

    response = client.get("/api/threads?limit=2&offset=1")
    assert response.status_code == 200
    data = response.json()

    assert data["total"] == 5
    assert len(data["threads"]) == 2
    assert data["limit"] == 2
    assert data["offset"] == 1


@patch("main.extract_context", return_value=MOCK_EXTRACTION_RESULT)
def test_list_threads_ordered_by_created_at_desc(mock_extract):
    """GET /api/threads should return most recent first."""
    for i in range(3):
        client.post(
            "/api/threads",
            json={
                **SAMPLE_CONVERSATION,
                "messages": [{"role": "user", "content": f"msg {i}"}],
            },
        )

    response = client.get("/api/threads")
    threads = response.json()["threads"]

    for i in range(len(threads) - 1):
        assert threads[i]["created_at"] >= threads[i + 1]["created_at"]


def test_list_threads_empty():
    """GET /api/threads with no data should return empty list."""
    response = client.get("/api/threads")
    assert response.status_code == 200
    data = response.json()
    assert data["threads"] == []
    assert data["total"] == 0


# ===== GET /api/threads/{id} =====


@patch("main.extract_context", return_value=MOCK_EXTRACTION_RESULT)
def test_get_thread_detail(mock_extract):
    """GET /api/threads/{id} should return full thread details."""
    create_resp = client.post("/api/threads", json=SAMPLE_CONVERSATION)
    thread_id = create_resp.json()["id"]

    response = client.get(f"/api/threads/{thread_id}")
    assert response.status_code == 200
    data = response.json()

    assert data["id"] == thread_id
    assert data["title"] == "Auth System Design with JWT Tokens"
    assert data["conversation_type"] == "build"
    assert data["raw_transcript_path"] is not None


def test_get_thread_not_found():
    """GET /api/threads/{id} with invalid ID should return 404."""
    response = client.get("/api/threads/nonexistent-id")
    assert response.status_code == 404
    assert response.json()["detail"] == "Thread not found"


# ===== GET /api/threads/{id}/raw =====


@patch("main.extract_context", return_value=MOCK_EXTRACTION_RESULT)
def test_get_raw_transcript(mock_extract):
    """GET /api/threads/{id}/raw should return the raw messages."""
    create_resp = client.post("/api/threads", json=SAMPLE_CONVERSATION)
    thread_id = create_resp.json()["id"]

    response = client.get(f"/api/threads/{thread_id}/raw")
    assert response.status_code == 200
    data = response.json()

    assert "messages" in data
    assert data["messages"] == SAMPLE_CONVERSATION["messages"]


def test_get_raw_transcript_not_found():
    """GET /api/threads/{id}/raw for nonexistent thread should return 404."""
    response = client.get("/api/threads/nonexistent-id/raw")
    assert response.status_code == 404


# ===== GET /api/threads/{id}/context =====


@patch("main.extract_context", return_value=MOCK_EXTRACTION_RESULT)
def test_get_summary_context(mock_extract):
    """GET /api/threads/{id}/context should return summary format by default."""
    create_resp = client.post("/api/threads", json=SAMPLE_CONVERSATION)
    thread_id = create_resp.json()["id"]

    response = client.get(f"/api/threads/{thread_id}/context")
    assert response.status_code == 200
    data = response.json()
    ctx = data["formatted_context"]

    assert data["format"] == "summary"
    assert ctx.startswith("[Context from ContextHub]")
    assert ctx.endswith("[End Context]")
    assert "Auth System Design with JWT Tokens" in ctx
    assert "Key takeaways:" in ctx
    assert "- Use JWT for stateless authentication" in ctx
    assert "Still open:" in ctx
    assert "- How to handle token revocation at scale?" in ctx
    assert "JWT token generation utility" in ctx


@patch("main.extract_context", return_value=MOCK_EXTRACTION_RESULT)
def test_get_full_context(mock_extract):
    """GET /api/threads/{id}/context?format=full should include full transcript."""
    create_resp = client.post("/api/threads", json=SAMPLE_CONVERSATION)
    thread_id = create_resp.json()["id"]

    response = client.get(f"/api/threads/{thread_id}/context?format=full")
    assert response.status_code == 200
    data = response.json()
    ctx = data["formatted_context"]

    assert data["format"] == "full"
    assert "estimated_tokens" in data
    assert ctx.startswith("[Full conversation from ContextHub]")
    assert ctx.endswith("[End Context]")
    assert "--- Full Transcript ---" in ctx
    assert "--- End Transcript ---" in ctx
    assert "User: Help me design an auth system using JWT" in ctx
    assert "Assistant:" in ctx


def test_get_context_not_found():
    """GET /api/threads/{id}/context for nonexistent thread should return 404."""
    response = client.get("/api/threads/nonexistent-id/context")
    assert response.status_code == 404


# ===== POST /api/threads/{id}/pull =====


@patch("main.extract_context", return_value=MOCK_EXTRACTION_RESULT)
def test_record_pull_event(mock_extract):
    """POST /api/threads/{id}/pull should create a pull event."""
    create_resp = client.post("/api/threads", json=SAMPLE_CONVERSATION)
    thread_id = create_resp.json()["id"]

    response = client.post(f"/api/threads/{thread_id}/pull")
    assert response.status_code == 201
    data = response.json()

    assert data["thread_id"] == thread_id
    assert data["id"] is not None
    assert data["pulled_at"] is not None


@patch("main.extract_context", return_value=MOCK_EXTRACTION_RESULT)
def test_record_multiple_pulls(mock_extract):
    """Multiple pull events should each be recorded separately."""
    create_resp = client.post("/api/threads", json=SAMPLE_CONVERSATION)
    thread_id = create_resp.json()["id"]

    pull1 = client.post(f"/api/threads/{thread_id}/pull").json()
    pull2 = client.post(f"/api/threads/{thread_id}/pull").json()

    assert pull1["id"] != pull2["id"]


def test_record_pull_not_found():
    """POST /api/threads/{id}/pull for nonexistent thread should return 404."""
    response = client.post("/api/threads/nonexistent-id/pull")
    assert response.status_code == 404


# ===== POST /api/threads/{id}/retry =====


@patch(
    "main.extract_context",
    side_effect=[Exception("First try failed"), MOCK_EXTRACTION_RESULT],
)
def test_retry_extraction(mock_extract):
    """POST /api/threads/{id}/retry should re-run extraction."""
    create_resp = client.post("/api/threads", json=SAMPLE_CONVERSATION)
    thread_id = create_resp.json()["id"]
    assert create_resp.json()["extraction_status"] == "failed"

    retry_resp = client.post(f"/api/threads/{thread_id}/retry")
    assert retry_resp.status_code == 200
    data = retry_resp.json()

    assert data["extraction_status"] == "done"
    assert data["title"] == "Auth System Design with JWT Tokens"
    assert data["extraction_error"] is None


def test_retry_extraction_not_found():
    """POST /api/threads/{id}/retry for nonexistent thread should return 404."""
    response = client.post("/api/threads/nonexistent-id/retry")
    assert response.status_code == 404


# ===== GET /api/stats =====


def test_stats_empty():
    """GET /api/stats with no data should return all zeros."""
    response = client.get("/api/stats")
    assert response.status_code == 200
    data = response.json()

    assert data["total_threads"] == 0
    assert data["total_pulls"] == 0
    assert data["threads_this_week"] == 0
    assert data["pulls_this_week"] == 0


@patch("main.extract_context", return_value=MOCK_EXTRACTION_RESULT)
def test_stats_with_data(mock_extract):
    """GET /api/stats should reflect actual counts."""
    resp1 = client.post("/api/threads", json=SAMPLE_CONVERSATION)
    resp2 = client.post("/api/threads", json=SAMPLE_CONVERSATION)

    tid = resp1.json()["id"]
    client.post(f"/api/threads/{tid}/pull")
    client.post(f"/api/threads/{tid}/pull")
    client.post(f"/api/threads/{resp2.json()['id']}/pull")

    response = client.get("/api/stats")
    data = response.json()

    assert data["total_threads"] == 2
    assert data["total_pulls"] == 3
    assert data["threads_this_week"] == 2
    assert data["pulls_this_week"] == 3


# ===== Model tests =====


def test_thread_to_dict_with_null_json_fields():
    """Thread.to_dict() should handle NULL JSON fields gracefully."""
    thread = Thread(
        id="test-id",
        source="claude",
        title="Test",
        summary="Test summary",
        key_takeaways=None,
        artifacts=None,
        open_threads=None,
        tags=None,
    )
    d = thread.to_dict()
    assert d["key_takeaways"] == []
    assert d["artifacts"] == []
    assert d["open_threads"] == []
    assert d["tags"] == []


def test_thread_to_dict_with_json_fields():
    """Thread.to_dict() should deserialize JSON text fields."""
    thread = Thread(
        id="test-id",
        source="claude",
        title="Test",
        conversation_type="decision",
        summary="Test summary",
        key_takeaways='["takeaway 1", "takeaway 2"]',
        artifacts="[]",
        open_threads='["open thread 1"]',
        tags='["tag1", "tag2"]',
    )
    d = thread.to_dict()
    assert d["key_takeaways"] == ["takeaway 1", "takeaway 2"]
    assert d["artifacts"] == []
    assert d["open_threads"] == ["open thread 1"]
    assert d["tags"] == ["tag1", "tag2"]
    assert d["conversation_type"] == "decision"


# ===== Extraction module tests =====


def test_extraction_prompt_exists():
    """Extraction module should have the prompt defined with correct fields."""
    from extraction import EXTRACTION_PROMPT

    assert "title" in EXTRACTION_PROMPT
    assert "summary" in EXTRACTION_PROMPT
    assert "conversation_type" in EXTRACTION_PROMPT
    assert "key_takeaways" in EXTRACTION_PROMPT
    assert "artifacts" in EXTRACTION_PROMPT
    assert "open_threads" in EXTRACTION_PROMPT
    assert "tags" in EXTRACTION_PROMPT


@patch("extraction.anthropic.Anthropic")
def test_extract_context_parses_json(mock_anthropic_cls):
    """extract_context should parse the API response as JSON."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(MOCK_EXTRACTION_RESULT))]
    mock_client.messages.create.return_value = mock_response

    from extraction import extract_context

    result = extract_context(SAMPLE_CONVERSATION["messages"])

    assert result["title"] == "Auth System Design with JWT Tokens"
    assert result["conversation_type"] == "build"
    assert len(result["key_takeaways"]) == 3
    assert len(result["tags"]) == 5
    assert len(result["open_threads"]) == 1


@patch("extraction.anthropic.Anthropic")
def test_extract_context_strips_markdown_fences(mock_anthropic_cls):
    """extract_context should strip ```json fences from response."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    fenced = f"```json\n{json.dumps(MOCK_EXTRACTION_RESULT)}\n```"
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=fenced)]
    mock_client.messages.create.return_value = mock_response

    from extraction import extract_context

    result = extract_context([{"role": "user", "content": "test"}])
    assert result["title"] == "Auth System Design with JWT Tokens"


@patch("extraction.anthropic.Anthropic")
def test_extract_context_validates_conversation_type(mock_anthropic_cls):
    """extract_context should default invalid conversation_type to 'other'."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    bad_result = {**MOCK_EXTRACTION_RESULT, "conversation_type": "invalid_type"}
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(bad_result))]
    mock_client.messages.create.return_value = mock_response

    from extraction import extract_context

    result = extract_context([{"role": "user", "content": "test"}])
    assert result["conversation_type"] == "other"


@patch("extraction.anthropic.Anthropic")
def test_extract_context_validates_artifacts(mock_anthropic_cls):
    """extract_context should validate artifact structure."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    result_with_bad_artifact = {
        **MOCK_EXTRACTION_RESULT,
        "artifacts": [
            {"content": "valid", "description": "test"},
            {"no_content_field": True},  # invalid - missing content
            "not even a dict",  # invalid
        ],
    }
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(result_with_bad_artifact))]
    mock_client.messages.create.return_value = mock_response

    from extraction import extract_context

    result = extract_context([{"role": "user", "content": "test"}])
    assert len(result["artifacts"]) == 1
    assert result["artifacts"][0]["content"] == "valid"


# ===== New helper function tests =====


def test_format_conversation():
    """format_conversation should produce readable text."""
    from extraction import format_conversation

    messages = [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]
    result = format_conversation(messages)
    assert "User: Hello" in result
    assert "Assistant: Hi there!" in result


def test_save_and_load_transcript():
    """save_transcript and load_transcript should round-trip messages."""
    from extraction import save_transcript, load_transcript

    messages = [
        {"role": "user", "content": "test message"},
        {"role": "assistant", "content": "response"},
    ]
    path = save_transcript("test-roundtrip", messages)
    assert os.path.exists(path)

    loaded = load_transcript(path)
    assert loaded == messages

    # Cleanup
    os.remove(path)


def test_extract_context_mock():
    """extract_context_mock should return valid structure without API key."""
    from extraction import extract_context_mock

    messages = [
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "hi"},
    ]
    result = extract_context_mock(messages)

    assert "title" in result
    assert "conversation_type" in result
    assert result["conversation_type"] == "other"
    assert "summary" in result
    assert isinstance(result["key_takeaways"], list)
    assert isinstance(result["artifacts"], list)
    assert isinstance(result["open_threads"], list)
    assert isinstance(result["tags"], list)
    assert "2 messages" in result["title"]


def test_validate_extraction_good():
    """validate_extraction should return no warnings for valid data."""
    from extraction import validate_extraction

    warnings = validate_extraction(MOCK_EXTRACTION_RESULT)
    assert warnings == []


def test_validate_extraction_bad():
    """validate_extraction should catch various issues."""
    from extraction import validate_extraction

    bad_data = {
        "title": "Hi",
        "summary": "Short",
        "conversation_type": "invalid",
        "key_takeaways": [],
        "tags": ["one"],
        "artifacts": [{"content": "something..."}],
    }
    warnings = validate_extraction(bad_data)

    assert any("Title is missing or too short" in w for w in warnings)
    assert any("Summary is missing or too short" in w for w in warnings)
    assert any("Invalid conversation_type" in w for w in warnings)
    assert any("No key takeaways" in w for w in warnings)
    assert any("Too few tags" in w for w in warnings)
    assert any("appears truncated" in w for w in warnings)


def test_validate_extraction_too_long_title():
    """validate_extraction should warn on title > 80 chars."""
    from extraction import validate_extraction

    data = {
        **MOCK_EXTRACTION_RESULT,
        "title": "A" * 81,
    }
    warnings = validate_extraction(data)
    assert any("unusually long" in w for w in warnings)


@patch("extraction.anthropic.Anthropic")
@patch.dict(os.environ, {"ANTHROPIC_API_KEY": "test-key"})
def test_process_thread(mock_anthropic_cls):
    """process_thread should orchestrate save + extraction."""
    mock_client = MagicMock()
    mock_anthropic_cls.return_value = mock_client

    mock_response = MagicMock()
    mock_response.content = [MagicMock(text=json.dumps(MOCK_EXTRACTION_RESULT))]
    mock_client.messages.create.return_value = mock_response

    from extraction import process_thread

    result = process_thread("test-process-id", SAMPLE_CONVERSATION["messages"])

    assert result["title"] == "Auth System Design with JWT Tokens"
    assert result["extraction_status"] == "done"
    assert result["message_count"] == 4
    assert os.path.exists(result["raw_transcript_path"])

    # Cleanup
    os.remove(result["raw_transcript_path"])


def test_process_thread_mock_mode():
    """process_thread with use_mock=True should skip API call."""
    from extraction import process_thread

    result = process_thread("test-mock-id", SAMPLE_CONVERSATION["messages"], use_mock=True)

    assert result["extraction_status"] == "done"
    assert "4 messages" in result["title"]
    assert os.path.exists(result["raw_transcript_path"])

    # Cleanup
    os.remove(result["raw_transcript_path"])


# ===== CORS test =====


def test_cors_headers():
    """API should include CORS headers."""
    response = client.options(
        "/api/threads",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert "access-control-allow-origin" in response.headers
