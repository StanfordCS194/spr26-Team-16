"""Integration tests for the push-share endpoints (/v1/pushes/*/shares,
/v1/shares/received) and the RLS surface added in migration 006.

What sharing must guarantee:
  - only the owner can create/revoke shares (recipients may remove themselves)
  - the recipient can read the push and its summary layers, never the
    transcript (neither the transcripts row nor the raw_transcript layer)
  - the recipient cannot rename/delete the shared push
  - revoking removes all access
  - shared pushes never leak into /v1/pushes/history or to third users
"""

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

OWNER_EMAIL = "share-owner@share-test.local"
RECIPIENT_EMAIL = "share-recipient@share-test.local"
OUTSIDER_EMAIL = "share-outsider@share-test.local"


@pytest_asyncio.fixture(scope="function")
async def async_engine(db_engine):
    from contexthub_backend.config import settings

    engine = make_async_engine(settings.async_database_url)
    auth_deps._set_engine(engine)
    yield engine
    await engine.dispose()


@pytest.fixture(scope="module")
def share_users():
    owner = uuid.uuid4()
    recipient = uuid.uuid4()
    outsider = uuid.uuid4()
    ws_owner = uuid.uuid4()
    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        conn.execute(
            "INSERT INTO interchange_format_versions (version, json_schema) "
            "VALUES ('ch.v0.1', '{}'::jsonb) ON CONFLICT DO NOTHING"
        )
        for uid, email in (
            (owner, OWNER_EMAIL),
            (recipient, RECIPIENT_EMAIL),
            (outsider, OUTSIDER_EMAIL),
        ):
            # auth.users lives in the auth-stub schema and survives alembic
            # downgrade; clear leftovers from prior runs so the fixed test
            # emails always map to this run's user ids.
            conn.execute("DELETE FROM auth.users WHERE email = %s", (email,))
            conn.execute(
                "INSERT INTO auth.users (id, email) VALUES (%s, %s)",
                (str(uid), email),
            )
        conn.execute(
            "INSERT INTO workspaces (id, user_id, name, slug) VALUES (%s, %s, %s, %s)",
            (str(ws_owner), str(owner), "Share WS", "share-ws"),
        )
    return {
        "owner": owner,
        "recipient": recipient,
        "outsider": outsider,
        "ws_owner": ws_owner,
    }


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
        "source": {"platform": "claude_ai", "captured_at": "2026-06-10T00:00:00Z"},
        "messages": [
            {"role": "user", "content": [{"type": "text", "text": "Secret transcript content"}]}
        ],
        "metadata": {"title": "Shared push title"},
    }


async def _create_ready_push(client, async_engine, share_users, idem: str) -> str:
    """Create a push as the owner and attach title/summary/details +
    raw_transcript summary layers, mirroring what the summarizer writes."""
    resp = await client.post(
        f"/v1/workspaces/{share_users['ws_owner']}/pushes",
        headers={"Authorization": f"Bearer {_jwt(share_users['owner'])}", "Idempotency-Key": idem},
        json=_push_payload(),
    )
    assert resp.status_code == 202
    push_id = resp.json()["push_id"]

    async with async_engine.begin() as conn:
        await conn.execute(
            text("update pushes set status = 'ready' where id = :push_id"),
            {"push_id": push_id},
        )
        await conn.execute(
            text(
                """
                insert into summaries (id, push_id, layer, content_json, content_markdown, model, prompt_version)
                values
                  (gen_random_uuid(), :push_id, 'title', cast(:title_json as jsonb), 'Share test title', 'fake-llm', 'summarize_v1'),
                  (gen_random_uuid(), :push_id, 'summary', cast(:summary_json as jsonb), 'Share test summary', 'fake-llm', 'summarize_v1'),
                  (gen_random_uuid(), :push_id, 'details', cast(:details_json as jsonb), :details_md, 'fake-llm', 'summarize_v1'),
                  (gen_random_uuid(), :push_id, 'raw_transcript', cast(:raw_json as jsonb), null, 'fake-llm', 'summarize_v1')
                """
            ),
            {
                "push_id": push_id,
                "title_json": json.dumps({"text": "Share test title"}),
                "summary_json": json.dumps({"text": "Share test summary"}),
                "details_json": json.dumps(
                    {
                        "summary": "Share test summary",
                        "key_takeaways": ["takeaway"],
                        "tags": ["share", "test"],
                    }
                ),
                "details_md": json.dumps({"summary": "Share test summary"}),
                "raw_json": json.dumps({"storage_path": "fake/path.json"}),
            },
        )
    return push_id


async def _share(client, share_users, push_id: str, email: str = RECIPIENT_EMAIL):
    return await client.post(
        f"/v1/pushes/{push_id}/shares",
        headers={"Authorization": f"Bearer {_jwt(share_users['owner'])}"},
        json={"recipient_email": email},
    )


@pytest.mark.integration
@pytest.mark.asyncio
async def test_owner_can_share_and_list_shares(client, async_engine, share_users):
    push_id = await _create_ready_push(client, async_engine, share_users, "idem-share-1")

    resp = await _share(client, share_users, push_id)
    assert resp.status_code == 201
    body = resp.json()
    assert body["push_id"] == push_id
    assert body["recipient_email"] == RECIPIENT_EMAIL
    assert body["owner_email"] == OWNER_EMAIL

    list_resp = await client.get(
        f"/v1/pushes/{push_id}/shares",
        headers={"Authorization": f"Bearer {_jwt(share_users['owner'])}"},
    )
    assert list_resp.status_code == 200
    items = list_resp.json()["items"]
    assert len(items) == 1
    assert items[0]["recipient_email"] == RECIPIENT_EMAIL


@pytest.mark.integration
@pytest.mark.asyncio
async def test_share_validation_errors(client, async_engine, share_users):
    push_id = await _create_ready_push(client, async_engine, share_users, "idem-share-2")

    unknown = await _share(client, share_users, push_id, email="nobody@share-test.local")
    assert unknown.status_code == 404

    not_an_email = await _share(client, share_users, push_id, email="not-an-email")
    assert not_an_email.status_code == 422

    to_self = await _share(client, share_users, push_id, email=OWNER_EMAIL)
    assert to_self.status_code == 422

    first = await _share(client, share_users, push_id)
    assert first.status_code == 201
    duplicate = await _share(client, share_users, push_id)
    assert duplicate.status_code == 422


@pytest.mark.integration
@pytest.mark.asyncio
async def test_only_owner_can_share(client, async_engine, share_users):
    push_id = await _create_ready_push(client, async_engine, share_users, "idem-share-3")
    resp = await _share(client, share_users, push_id)
    assert resp.status_code == 201

    # The recipient can see the push but must not be able to share it onward.
    reshare = await client.post(
        f"/v1/pushes/{push_id}/shares",
        headers={"Authorization": f"Bearer {_jwt(share_users['recipient'])}"},
        json={"recipient_email": OUTSIDER_EMAIL},
    )
    assert reshare.status_code == 403

    # An unrelated user can't even see the push.
    outsider_share = await client.post(
        f"/v1/pushes/{push_id}/shares",
        headers={"Authorization": f"Bearer {_jwt(share_users['outsider'])}"},
        json={"recipient_email": RECIPIENT_EMAIL},
    )
    assert outsider_share.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recipient_sees_share_in_received_and_detail(client, async_engine, share_users):
    push_id = await _create_ready_push(client, async_engine, share_users, "idem-share-4")
    resp = await _share(client, share_users, push_id)
    assert resp.status_code == 201

    received = await client.get(
        "/v1/shares/received",
        headers={"Authorization": f"Bearer {_jwt(share_users['recipient'])}"},
    )
    assert received.status_code == 200
    items = [i for i in received.json()["items"] if i["push_id"] == push_id]
    assert len(items) == 1
    item = items[0]
    assert item["owner_email"] == OWNER_EMAIL
    assert item["title"] == "Share test title"
    assert item["summary"] == "Share test summary"
    assert item["details"]["tags"] == ["share", "test"]

    detail = await client.get(
        f"/v1/pushes/{push_id}",
        headers={"Authorization": f"Bearer {_jwt(share_users['recipient'])}"},
    )
    assert detail.status_code == 200
    body = detail.json()
    assert body["is_owner"] is False
    assert body["shared_by"] == OWNER_EMAIL
    # Transcript access is owner-only: the transcripts row is hidden by RLS
    # and the raw_transcript summary layer is excluded by policy.
    assert body["raw_transcript"] is None
    assert body["transcript_message_count"] is None
    layers = {layer["layer"] for layer in body["summaries"]}
    assert layers == {"title", "summary", "details"}

    # The outsider still gets a 404 on the same push.
    outsider_detail = await client.get(
        f"/v1/pushes/{push_id}",
        headers={"Authorization": f"Bearer {_jwt(share_users['outsider'])}"},
    )
    assert outsider_detail.status_code == 404

    # Shared pushes must not leak into the recipient's own history.
    history = await client.get(
        "/v1/pushes/history?limit=50",
        headers={"Authorization": f"Bearer {_jwt(share_users['recipient'])}"},
    )
    assert history.status_code == 200
    assert all(entry["id"] != push_id for entry in history.json()["items"])


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recipient_cannot_modify_shared_push(client, async_engine, share_users):
    push_id = await _create_ready_push(client, async_engine, share_users, "idem-share-5")
    resp = await _share(client, share_users, push_id)
    assert resp.status_code == 201

    rename = await client.patch(
        f"/v1/pushes/{push_id}",
        headers={"Authorization": f"Bearer {_jwt(share_users['recipient'])}"},
        json={"title": "hijacked"},
    )
    assert rename.status_code == 403

    delete = await client.delete(
        f"/v1/pushes/{push_id}",
        headers={"Authorization": f"Bearer {_jwt(share_users['recipient'])}"},
    )
    assert delete.status_code == 403


@pytest.mark.integration
@pytest.mark.asyncio
async def test_owner_revoke_removes_access(client, async_engine, share_users):
    push_id = await _create_ready_push(client, async_engine, share_users, "idem-share-6")
    share_resp = await _share(client, share_users, push_id)
    assert share_resp.status_code == 201
    share_id = share_resp.json()["id"]

    revoke = await client.delete(
        f"/v1/pushes/{push_id}/shares/{share_id}",
        headers={"Authorization": f"Bearer {_jwt(share_users['owner'])}"},
    )
    assert revoke.status_code == 204

    received = await client.get(
        "/v1/shares/received",
        headers={"Authorization": f"Bearer {_jwt(share_users['recipient'])}"},
    )
    assert all(i["push_id"] != push_id for i in received.json()["items"])

    detail = await client.get(
        f"/v1/pushes/{push_id}",
        headers={"Authorization": f"Bearer {_jwt(share_users['recipient'])}"},
    )
    assert detail.status_code == 404


@pytest.mark.integration
@pytest.mark.asyncio
async def test_recipient_can_remove_self(client, async_engine, share_users):
    push_id = await _create_ready_push(client, async_engine, share_users, "idem-share-7")
    share_resp = await _share(client, share_users, push_id)
    assert share_resp.status_code == 201
    share_id = share_resp.json()["id"]

    remove = await client.delete(
        f"/v1/pushes/{push_id}/shares/{share_id}",
        headers={"Authorization": f"Bearer {_jwt(share_users['recipient'])}"},
    )
    assert remove.status_code == 204

    owner_list = await client.get(
        f"/v1/pushes/{push_id}/shares",
        headers={"Authorization": f"Bearer {_jwt(share_users['owner'])}"},
    )
    assert owner_list.status_code == 200
    assert owner_list.json()["items"] == []


@pytest.mark.integration
@pytest.mark.asyncio
async def test_deleted_push_disappears_from_received(client, async_engine, share_users):
    push_id = await _create_ready_push(client, async_engine, share_users, "idem-share-8")
    assert (await _share(client, share_users, push_id)).status_code == 201

    delete = await client.delete(
        f"/v1/pushes/{push_id}",
        headers={"Authorization": f"Bearer {_jwt(share_users['owner'])}"},
    )
    assert delete.status_code == 204

    received = await client.get(
        "/v1/shares/received",
        headers={"Authorization": f"Bearer {_jwt(share_users['recipient'])}"},
    )
    assert all(i["push_id"] != push_id for i in received.json()["items"])
