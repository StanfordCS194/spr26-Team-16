"""Fixture dataset generator — ≥50 workspaces / ≥500 pushes.

Usage (requires DATABASE_URL in environment):
    uv run --package contexthub-backend python scripts/gen_fixtures.py

Generates a deterministic dataset suitable for Alembic up+down CI testing.
Rows cover every enum value and every nullable/optional field so migrations
are exercised against realistic data, not just empty tables.
"""

from __future__ import annotations

import hashlib
import os
import random
import uuid
from datetime import datetime, timezone

from faker import Faker
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from contexthub_backend.db.models import (
    AuditLog,
    InterchangeFormatVersion,
    Profile,
    Pull,
    Push,
    PushRelationship,
    PushTag,
    Summary,
    SummaryFeedback,
    Tag,
    Transcript,
    Workspace,
)
from contexthub_backend.db.short_id import uuid7

SEED = 42
N_USERS = 10
N_WORKSPACES = 60   # ≥50
N_PUSHES = 550      # ≥500
N_TAGS_PER_WORKSPACE = 4
N_PULLS = 80
N_AUDIT_ROWS = 100

SOURCE_PLATFORMS = ["claude_ai", "chatgpt", "gemini"]
PUSH_STATUSES = ["pending", "processing", "ready", "failed"]
SUMMARY_LAYERS = ["commit_message", "structured_block", "raw_transcript"]
RELATION_TYPES = ["continuation", "reference", "supersession"]

fake = Faker()
fake.seed_instance(SEED)
random.seed(SEED)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _insert_auth_users(conn, user_ids: list[uuid.UUID]) -> None:
    """Insert rows into auth.users (exists in stub; no-op in real Supabase)."""
    for uid in user_ids:
        conn.execute(
            text(
                "INSERT INTO auth.users (id, email) VALUES (:id, :email) "
                "ON CONFLICT (id) DO NOTHING"
            ),
            {"id": str(uid), "email": fake.unique.email()},
        )


def generate(database_url: str) -> None:
    engine = create_engine(database_url)

    user_ids = [uuid7() for _ in range(N_USERS)]

    with engine.connect() as conn:
        _insert_auth_users(conn, user_ids)
        conn.commit()

    # Seed ch.v0.1 interchange version
    with Session(engine) as session:
        if not session.get(InterchangeFormatVersion, "ch.v0.1"):
            session.add(
                InterchangeFormatVersion(
                    version="ch.v0.1",
                    json_schema={"$schema": "ch.v0.1", "type": "object"},
                )
            )
            session.commit()

    with Session(engine) as session:
        # Profiles
        for uid in user_ids:
            session.add(Profile(user_id=uid, display_name=fake.name()))
        session.flush()

        # Workspaces (≥50, spread across users)
        workspaces: list[Workspace] = []
        for i in range(N_WORKSPACES):
            uid = user_ids[i % N_USERS]
            ws = Workspace(
                id=uuid7(),
                user_id=uid,
                name=fake.bs().title()[:60],
                slug=f"ws-{i:04d}",
                settings_json={"default_resolution": "structured_block"} if i % 3 == 0 else None,
            )
            session.add(ws)
            workspaces.append(ws)
        session.flush()

        # Tags
        all_tags: list[Tag] = []
        for ws in workspaces:
            for j in range(N_TAGS_PER_WORKSPACE):
                tag = Tag(
                    id=uuid7(),
                    workspace_id=ws.id,
                    name=fake.word(),
                    slug=f"tag-{fake.lexify('????')}",
                )
                session.add(tag)
                all_tags.append(tag)
        session.flush()

        # Pushes (≥500)
        pushes: list[Push] = []
        for i in range(N_PUSHES):
            ws = workspaces[i % N_WORKSPACES]
            platform = SOURCE_PLATFORMS[i % len(SOURCE_PLATFORMS)]
            status = PUSH_STATUSES[i % len(PUSH_STATUSES)]
            push = Push(
                id=uuid7(),
                workspace_id=ws.id,
                user_id=ws.user_id,
                source_platform=platform,
                source_url=f"https://claude.ai/chat/{fake.uuid4()}" if platform == "claude_ai" else None,
                source_conversation_id=str(fake.uuid4()) if i % 2 == 0 else None,
                interchange_version="ch.v0.1",
                title=fake.sentence(nb_words=5)[:100] if i % 3 != 0 else None,
                commit_message=fake.sentence(nb_words=8)[:200],
                status=status,
                failure_reason="LLM JSON parse error" if status == "failed" else None,
                idempotency_key=str(fake.uuid4()),
            )
            session.add(push)
            pushes.append(push)

            # push_tags: attach 0–2 tags from the same workspace
            ws_tags = [t for t in all_tags if t.workspace_id == ws.id]
            for tag in random.sample(ws_tags, min(2, len(ws_tags))):
                session.add(PushTag(push_id=push.id, tag_id=tag.id))

        session.flush()

        # Summaries (3 layers per "ready" push)
        ready_pushes = [p for p in pushes if p.status == "ready"]
        for push in ready_pushes:
            for layer in SUMMARY_LAYERS:
                content_md = fake.paragraph(nb_sentences=4)
                s = Summary(
                    id=uuid7(),
                    push_id=push.id,
                    layer=layer,
                    content_json={"text": content_md} if layer == "commit_message" else {"spec_version": "ch.v0.1", "decisions": []},
                    content_markdown=content_md,
                    model="claude-haiku-4-5",
                    prompt_version="summarize_v1.0",
                    latency_ms=random.randint(800, 5000),
                    input_tokens=random.randint(500, 8000),
                    output_tokens=random.randint(100, 1200),
                    cost_usd=round(random.uniform(0.0001, 0.02), 6),
                    quality_score=round(random.uniform(3.0, 5.0), 2) if random.random() > 0.5 else None,
                )
                session.add(s)
        session.flush()

        # Transcripts for ready pushes
        for push in ready_pushes[:100]:
            session.add(
                Transcript(
                    push_id=push.id,
                    storage_path=f"transcripts/{push.user_id}/{push.id}.json",
                    sha256=hashlib.sha256(str(push.id).encode()).hexdigest(),
                    size_bytes=random.randint(1024, 512_000),
                    message_count=random.randint(4, 200),
                )
            )

        # Push relationships (a few continuation edges)
        if len(ready_pushes) >= 10:
            for i in range(0, min(20, len(ready_pushes) - 1), 2):
                session.add(
                    PushRelationship(
                        id=uuid7(),
                        from_push_id=ready_pushes[i].id,
                        to_push_id=ready_pushes[i + 1].id,
                        relation_type=RELATION_TYPES[i % len(RELATION_TYPES)],
                    )
                )

        # Summary feedback
        summaries_sample = session.query(Summary).limit(50).all()
        for s in summaries_sample:
            if random.random() > 0.6:
                session.add(
                    SummaryFeedback(
                        id=uuid7(),
                        summary_id=s.id,
                        user_id=user_ids[0],
                        score=random.randint(1, 5),
                        comment=fake.sentence() if random.random() > 0.5 else None,
                    )
                )

        # Pulls
        for i in range(N_PULLS):
            push_sample = random.sample(ready_pushes, min(3, len(ready_pushes)))
            session.add(
                Pull(
                    id=uuid7(),
                    user_id=user_ids[i % N_USERS],
                    target_platform="claude_ai",
                    origin="extension" if i % 2 == 0 else "dashboard",
                    resolution=SUMMARY_LAYERS[i % len(SUMMARY_LAYERS)],
                    push_ids=[str(p.id) for p in push_sample],
                    workspace_ids=list({str(p.workspace_id) for p in push_sample}),
                    token_estimate=random.randint(200, 4000),
                )
            )

        # Audit log
        actions = ["push.create", "pull.inject", "token.mint", "workspace.create", "push.delete"]
        for i in range(N_AUDIT_ROWS):
            session.add(
                AuditLog(
                    id=uuid7(),
                    user_id=user_ids[i % N_USERS],
                    action=actions[i % len(actions)],
                    resource_type="push" if "push" in actions[i % len(actions)] else "workspace",
                    resource_id=str(uuid.uuid4()),
                    request_id=str(fake.uuid4()),
                    ip=fake.ipv4(),
                    user_agent=fake.user_agent(),
                    metadata_json={"source": "extension"},
                )
            )

        session.commit()

    print(
        f"Generated {N_USERS} users, {N_WORKSPACES} workspaces, "
        f"{N_PUSHES} pushes, {len(ready_pushes) * 3} summaries, "
        f"{N_PULLS} pulls, {N_AUDIT_ROWS} audit rows."
    )


if __name__ == "__main__":
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/contexthub_dev",
    )
    generate(url)
