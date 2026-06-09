"""RLS integration test — asserts user A cannot read user B's rows.

Requires DATABASE_URL pointing to a live Postgres (with pgvector + auth stub).
The session-scoped db_engine from conftest.py runs migrations and loads fixtures
before these tests execute.

Strategy:
  - Insert two fresh users directly into auth.users
  - Insert a workspace + push for each user
  - For each user, open a transaction that:
      1. Grants ch_authenticated to the current session user (required to SET ROLE)
      2. SET LOCAL ROLE ch_authenticated
      3. SET LOCAL "app.current_user_id" = <user_uid>  (drives auth.uid())
      4. SELECT from workspaces / pushes
  - Assert each user sees only their own rows
"""

from __future__ import annotations

import uuid

import psycopg
import pytest

from tests.conftest import _psycopg_url
from contexthub_backend.db.short_id import uuid7


@pytest.fixture(scope="module")
def rls_users(db_engine):
    """Create two isolated test users and their workspaces/pushes in the DB."""
    user_a = uuid7()
    user_b = uuid7()

    url = _psycopg_url()
    with psycopg.connect(url, autocommit=True) as conn:
        # Create auth.users rows
        for uid, email in [(user_a, "rls-alice@test.local"), (user_b, "rls-bob@test.local")]:
            conn.execute(
                "INSERT INTO auth.users (id, email) VALUES (%s, %s) ON CONFLICT DO NOTHING",
                (str(uid), email),
            )

        # Create profiles
        for uid in [user_a, user_b]:
            conn.execute(
                "INSERT INTO profiles (user_id) VALUES (%s) ON CONFLICT DO NOTHING",
                (str(uid),),
            )

        # Ensure ch.v0.1 interchange version exists (fixture loader should have it)
        conn.execute(
            "INSERT INTO interchange_format_versions (version, json_schema) "
            "VALUES ('ch.v0.1', '{}'::jsonb) ON CONFLICT DO NOTHING"
        )

        # Workspaces — one per user
        ws_a = uuid7()
        ws_b = uuid7()
        conn.execute(
            "INSERT INTO workspaces (id, user_id, name, slug) VALUES (%s, %s, %s, %s)",
            (str(ws_a), str(user_a), "Alice RLS WS", "alice-rls"),
        )
        conn.execute(
            "INSERT INTO workspaces (id, user_id, name, slug) VALUES (%s, %s, %s, %s)",
            (str(ws_b), str(user_b), "Bob RLS WS", "bob-rls"),
        )

        # Pushes — one per user
        push_a = uuid7()
        push_b = uuid7()
        for push_id, ws_id, uid in [(push_a, ws_a, user_a), (push_b, ws_b, user_b)]:
            conn.execute(
                """
                INSERT INTO pushes
                  (id, workspace_id, user_id, source_platform, interchange_version, status)
                VALUES (%s, %s, %s, 'claude_ai', 'ch.v0.1', 'ready')
                """,
                (str(push_id), str(ws_id), str(uid)),
            )

        # Grant ch_authenticated to the connecting role so SET ROLE is allowed
        conn.execute("GRANT ch_authenticated TO CURRENT_USER")

    return {
        "user_a": user_a, "user_b": user_b,
        "ws_a": ws_a, "ws_b": ws_b,
        "push_a": push_a, "push_b": push_b,
    }


def _query_as_user(conn, uid: uuid.UUID, table: str) -> list[str]:
    """Return IDs visible to `uid` in `table` using RLS context."""
    with conn.transaction():
        conn.execute("SET LOCAL ROLE ch_authenticated")
        conn.execute(
            "SELECT set_config('app.current_user_id', %s, true)",
            (str(uid),),
        )
        rows = conn.execute(f"SELECT id FROM {table}").fetchall()  # noqa: S608
    return [str(r[0]) for r in rows]


@pytest.mark.integration
class TestRlsWorkspaces:
    def test_user_a_sees_only_own_workspace(self, db_engine, rls_users):
        url = _psycopg_url()
        with psycopg.connect(url) as conn:
            visible = _query_as_user(conn, rls_users["user_a"], "workspaces")
        assert str(rls_users["ws_a"]) in visible
        assert str(rls_users["ws_b"]) not in visible

    def test_user_b_sees_only_own_workspace(self, db_engine, rls_users):
        url = _psycopg_url()
        with psycopg.connect(url) as conn:
            visible = _query_as_user(conn, rls_users["user_b"], "workspaces")
        assert str(rls_users["ws_b"]) in visible
        assert str(rls_users["ws_a"]) not in visible

    def test_no_uid_sees_nothing(self, db_engine, rls_users):
        url = _psycopg_url()
        with psycopg.connect(url) as conn:
            with conn.transaction():
                conn.execute("SET LOCAL ROLE ch_authenticated")
                conn.execute("SET LOCAL app.current_user_id TO ''")
                rows = conn.execute("SELECT id FROM workspaces").fetchall()
        # With a NULL auth.uid(), the policy USING clause is false for all rows
        ids = [str(r[0]) for r in rows]
        assert str(rls_users["ws_a"]) not in ids
        assert str(rls_users["ws_b"]) not in ids


@pytest.mark.integration
class TestRlsPushes:
    def test_user_a_sees_only_own_pushes(self, db_engine, rls_users):
        url = _psycopg_url()
        with psycopg.connect(url) as conn:
            visible = _query_as_user(conn, rls_users["user_a"], "pushes")
        assert str(rls_users["push_a"]) in visible
        assert str(rls_users["push_b"]) not in visible

    def test_user_b_sees_only_own_pushes(self, db_engine, rls_users):
        url = _psycopg_url()
        with psycopg.connect(url) as conn:
            visible = _query_as_user(conn, rls_users["user_b"], "pushes")
        assert str(rls_users["push_b"]) in visible
        assert str(rls_users["push_a"]) not in visible


@pytest.mark.integration
class TestRlsProfiles:
    def test_user_a_sees_only_own_profile(self, db_engine, rls_users):
        url = _psycopg_url()
        with psycopg.connect(url) as conn:
            with conn.transaction():
                conn.execute("SET LOCAL ROLE ch_authenticated")
                conn.execute(
                    "SELECT set_config('app.current_user_id', %s, true)",
                    (str(rls_users["user_a"]),),
                )
                rows = conn.execute("SELECT user_id FROM profiles").fetchall()
        ids = [str(r[0]) for r in rows]
        assert str(rls_users["user_a"]) in ids
        assert str(rls_users["user_b"]) not in ids
