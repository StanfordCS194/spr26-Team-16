"""Small local-dev seed — creates 2 users, 3 workspaces, 10 pushes.

Usage:
    DATABASE_URL=postgresql+psycopg://postgres:postgres@localhost:5432/contexthub_dev \
        uv run --package contexthub-backend python scripts/seed_dev.py
"""

from __future__ import annotations

import os

from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

from contexthub_backend.db.models import (
    AuditLog,
    InterchangeFormatVersion,
    Profile,
    Push,
    Summary,
    Workspace,
)
from contexthub_backend.db.short_id import uuid7


def seed(database_url: str) -> None:
    engine = create_engine(database_url)

    user_a = uuid7()
    user_b = uuid7()

    with engine.connect() as conn:
        for uid, email in [(user_a, "alice@example.com"), (user_b, "bob@example.com")]:
            conn.execute(
                text(
                    "INSERT INTO auth.users (id, email) VALUES (:id, :email) "
                    "ON CONFLICT (id) DO NOTHING"
                ),
                {"id": str(uid), "email": email},
            )
        conn.commit()

    with Session(engine) as session:
        # Interchange spec version
        if not session.get(InterchangeFormatVersion, "ch.v0.1"):
            session.add(
                InterchangeFormatVersion(
                    version="ch.v0.1",
                    json_schema={"$schema": "ch.v0.1", "type": "object"},
                )
            )

        # Profiles
        session.add(Profile(user_id=user_a, display_name="Alice"))
        session.add(Profile(user_id=user_b, display_name="Bob"))
        session.flush()

        # Workspaces
        ws1 = Workspace(id=uuid7(), user_id=user_a, name="Alice Main", slug="alice-main")
        ws2 = Workspace(id=uuid7(), user_id=user_a, name="Alice Research", slug="alice-research")
        ws3 = Workspace(id=uuid7(), user_id=user_b, name="Bob Projects", slug="bob-projects")
        session.add_all([ws1, ws2, ws3])
        session.flush()

        # Pushes
        pushes = []
        for i in range(5):
            p = Push(
                id=uuid7(),
                workspace_id=ws1.id,
                user_id=user_a,
                source_platform="claude_ai",
                source_url=f"https://claude.ai/chat/dev-{i:03d}",
                interchange_version="ch.v0.1",
                commit_message=f"Dev push #{i + 1}: explored topic {i}",
                status="ready",
            )
            session.add(p)
            pushes.append(p)

        for i in range(5):
            p = Push(
                id=uuid7(),
                workspace_id=ws3.id,
                user_id=user_b,
                source_platform="claude_ai",
                interchange_version="ch.v0.1",
                commit_message=f"Bob push #{i + 1}",
                status="ready",
            )
            session.add(p)
            pushes.append(p)

        session.flush()

        # One summary per push
        for push in pushes:
            session.add(
                Summary(
                    id=uuid7(),
                    push_id=push.id,
                    layer="commit_message",
                    content_json={"text": push.commit_message},
                    content_markdown=push.commit_message,
                    model="claude-haiku-4-5",
                    prompt_version="summarize_v1.0",
                )
            )

        # Audit log
        session.add(
            AuditLog(
                id=uuid7(),
                user_id=user_a,
                action="workspace.create",
                resource_type="workspace",
                resource_id=str(ws1.id),
                metadata_json={"source": "seed"},
            )
        )

        session.commit()

    print("Dev seed complete: 2 users, 3 workspaces, 10 pushes.")


if __name__ == "__main__":
    url = os.environ.get(
        "DATABASE_URL",
        "postgresql+psycopg://postgres:postgres@localhost:5432/contexthub_dev",
    )
    seed(url)
