from __future__ import annotations

import json
import uuid

import psycopg
import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

from contexthub_backend.auth import dependencies as auth_deps
from contexthub_backend.auth.jwt import make_test_jwt
from contexthub_backend.db.base import make_async_engine
from tests.conftest import _psycopg_url

TEST_JWT_SECRET = "test-secret-not-for-production-at-least-32-bytes"


@pytest_asyncio.fixture(scope="function")
async def async_engine(db_engine):
    from contexthub_backend.config import settings

    engine = make_async_engine(settings.async_database_url)
    auth_deps._set_engine(engine)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="module")
def push_users_and_workspaces():
    user_a = uuid.uuid4()
    user_b = uuid.uuid4()
    ws_a = uuid.uuid4()
    ws_b = uuid.uuid4()
    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO interchange_format_versions (version, json_schema) "
            "VALUES ('ch.v0.1', '{}'::jsonb) ON CONFLICT DO NOTHING"
        )
        for uid in (user_a, user_b):
            conn.execute(
                "INSERT INTO auth.users (id, email) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (str(uid), f"{str(uid).replace('-', '')[:16]}@push-test.local"),
            )
        conn.execute(
            "INSERT INTO workspaces (id, user_id, name, slug) VALUES (%s, %s, %s, %s)",
            (str(ws_a), str(user_a), "A", "a"),
        )
        conn.execute(
            "INSERT INTO workspaces (id, user_id, name, slug) VALUES (%s, %s, %s, %s)",
            (str(ws_b), str(user_b), "B", "b"),
        )
    return {"user_a": user_a, "user_b": user_b, "ws_a": ws_a, "ws_b": ws_b}


@pytest_asyncio.fixture(scope="function")
async def client(async_engine):
    import contexthub_backend.config as cfg_module
    from contexthub_backend.api.app import create_app
    from contexthub_backend.config import Settings

    cfg_module.settings = Settings(
        database_url=cfg_module.settings.database_url,
        supabase_jwt_secret=TEST_JWT_SECRET,
    )
    app = create_app(engine=async_engine)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        yield c


def _jwt(user_id: uuid.UUID) -> str:
    return make_test_jwt(user_id, TEST_JWT_SECRET)


def _push_payload() -> dict:
    return {
        "spec_version": "ch.v0.1",
        "source": {"platform": "claude_ai", "captured_at": "2026-04-23T00:00:00Z"},
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "Summarize this thread"}]}
        ],
        "metadata": {"title": "Push title"},
    }


@pytest.mark.integration
@pytest.mark.asyncio
async def test_create_push_pending_and_transcript_written(client, async_engine, push_users_and_workspaces):
    ws = push_users_and_workspaces["ws_a"]
    user = push_users_and_workspaces["user_a"]
    response = await client.post(
        f"/v1/workspaces/{ws}/pushes",
        headers={"Authorization": f"Bearer {_jwt(user)}", "Idempotency-Key": "idem-push-1"},
        json=_push_payload(),
    )
    assert response.status_code == 202
    body = response.json()
    assert body["status"] == "pending"
    push_id = body["push_id"]

    async with async_engine.begin() as conn:
        push_row = await conn.execute(
            text("select status from pushes where id = :id"),
            {"id": push_id},
        )
        transcript_row = await conn.execute(
            text("select storage_path from transcripts where push_id = :id"),
            {"id": push_id},
        )
    assert push_row.scalar_one() == "pending"
    assert transcript_row.scalar_one().endswith(".json")


@pytest.mark.integration
@pytest.mark.asyncio
async def test_rls_user_a_cannot_push_to_user_b_workspace(client, push_users_and_workspaces):
    ws_b = push_users_and_workspaces["ws_b"]
    user_a = push_users_and_workspaces["user_a"]
    response = await client.post(
        f"/v1/workspaces/{ws_b}/pushes",
        headers={"Authorization": f"Bearer {_jwt(user_a)}"},
        json=_push_payload(),
    )
    assert response.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_history_returns_only_callers_pushes_with_summaries(client, async_engine, push_users_and_workspaces):
    ws_a = push_users_and_workspaces["ws_a"]
    ws_b = push_users_and_workspaces["ws_b"]
    user_a = push_users_and_workspaces["user_a"]
    user_b = push_users_and_workspaces["user_b"]

    push_a_resp = await client.post(
        f"/v1/workspaces/{ws_a}/pushes",
        headers={"Authorization": f"Bearer {_jwt(user_a)}", "Idempotency-Key": "idem-history-a"},
        json=_push_payload(),
    )
    assert push_a_resp.status_code == 202
    push_a_id = push_a_resp.json()["push_id"]

    push_b_resp = await client.post(
        f"/v1/workspaces/{ws_b}/pushes",
        headers={"Authorization": f"Bearer {_jwt(user_b)}", "Idempotency-Key": "idem-history-b"},
        json=_push_payload(),
    )
    assert push_b_resp.status_code == 202

    async with async_engine.begin() as conn:
        await conn.execute(
            text(
                """
                insert into summaries (push_id, layer, content_json, content_markdown, model, prompt_version)
                values
                  (:push_id, 'commit_message', cast(:commit_json as jsonb), :commit_md, 'fake-llm', 'summarize_v1'),
                  (:push_id, 'structured_block', cast(:structured_json as jsonb), :structured_md, 'fake-llm', 'summarize_v1')
                """
            ),
            {
                "push_id": push_a_id,
                "commit_json": json.dumps({"text": "History test commit summary"}),
                "commit_md": "History test commit summary",
                "structured_json": json.dumps(
                    {
                        "spec_version": "ch.v0.1",
                        "decisions": [],
                        "artifacts": [],
                        "open_questions": [],
                        "assumptions": [],
                        "constraints": [],
                    }
                ),
                "structured_md": "## Decisions\n\n- none\n",
            },
        )

    response = await client.get(
        "/v1/pushes/history?limit=25",
        headers={"Authorization": f"Bearer {_jwt(user_a)}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert "items" in body
    assert len(body["items"]) >= 1

    matching = [item for item in body["items"] if item["id"] == push_a_id]
    assert len(matching) == 1
    item = matching[0]
    assert item["workspace_id"] == str(ws_a)
    assert item["commit_message"] == "History test commit summary"
    assert item["structured_summary_markdown"] == "## Decisions\n\n- none\n"
    assert "Summarize this thread" in (item["raw_transcript"] or "")

    # Caller should not see other users' pushes.
    assert all(entry["workspace_id"] != str(ws_b) for entry in body["items"])
