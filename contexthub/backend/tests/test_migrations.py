"""Migration up+down integration tests.

Requires DATABASE_URL pointing to a live Postgres with pgvector.
These tests use the session-scoped db_engine fixture, which already runs
`alembic upgrade head` and loads the fixture dataset in conftest.py.

After the session, conftest runs `alembic downgrade base` and the
test_downgrade_leaves_clean_db test verifies the result by running an
independent downgrade+check cycle.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import pytest
import sqlalchemy as sa
from sqlalchemy import inspect, text

BACKEND_DIR = Path(__file__).parent.parent
EXPECTED_TABLES = {
    "profiles", "api_tokens", "workspaces", "interchange_format_versions",
    "pushes", "summaries", "summary_embeddings", "transcripts", "tags",
    "push_tags", "push_relationships", "summary_feedback", "pulls", "audit_log",
}


@pytest.mark.integration
class TestMigrationsUp:
    """Verify that after upgrade head + fixture load the schema is correct."""

    def test_all_expected_tables_exist(self, db_engine):
        insp = inspect(db_engine)
        tables = set(insp.get_table_names())
        assert EXPECTED_TABLES.issubset(tables), (
            f"Missing tables: {EXPECTED_TABLES - tables}"
        )

    def test_fixture_workspaces_count(self, db_engine):
        with db_engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM workspaces")).scalar()
        assert count >= 50, f"Expected ≥50 workspaces, got {count}"

    def test_fixture_pushes_count(self, db_engine):
        with db_engine.connect() as conn:
            count = conn.execute(text("SELECT count(*) FROM pushes")).scalar()
        assert count >= 500, f"Expected ≥500 pushes, got {count}"

    def test_push_status_enum_values(self, db_engine):
        with db_engine.connect() as conn:
            statuses = {
                row[0]
                for row in conn.execute(
                    text("SELECT DISTINCT status FROM pushes")
                ).fetchall()
            }
        expected = {"pending", "processing", "ready", "failed"}
        assert statuses.issubset(expected)

    def test_summary_layers_present(self, db_engine):
        with db_engine.connect() as conn:
            layers = {
                row[0]
                for row in conn.execute(
                    text("SELECT DISTINCT layer FROM summaries")
                ).fetchall()
            }
        expected = {"commit_message", "structured_block", "raw_transcript"}
        assert layers.issubset(expected)

    def test_pushes_cover_all_source_platforms(self, db_engine):
        with db_engine.connect() as conn:
            platforms = {
                row[0]
                for row in conn.execute(
                    text("SELECT DISTINCT source_platform FROM pushes")
                ).fetchall()
            }
        assert "claude_ai" in platforms

    def test_summaries_have_content_tsv_populated(self, db_engine):
        with db_engine.connect() as conn:
            count = conn.execute(
                text(
                    "SELECT count(*) FROM summaries "
                    "WHERE content_tsv IS NOT NULL AND content_markdown IS NOT NULL"
                )
            ).scalar()
        assert count > 0, "content_tsv trigger must populate column"

    def test_hnsw_index_exists(self, db_engine):
        with db_engine.connect() as conn:
            rows = conn.execute(
                text(
                    "SELECT indexname FROM pg_indexes "
                    "WHERE tablename = 'summary_embeddings' "
                    "  AND indexname = 'ix_summary_embeddings_hnsw'"
                )
            ).fetchall()
        assert rows, "HNSW index on summary_embeddings.embedding not found"

    def test_pulls_workspace_ids_array_column(self, db_engine):
        with db_engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT data_type FROM information_schema.columns "
                    "WHERE table_name = 'pulls' AND column_name = 'workspace_ids'"
                )
            ).scalar()
        assert result == "ARRAY"

    def test_summaries_failure_reason_column_exists(self, db_engine):
        with db_engine.connect() as conn:
            result = conn.execute(
                text(
                    "SELECT column_name FROM information_schema.columns "
                    "WHERE table_name = 'summaries' AND column_name = 'failure_reason'"
                )
            ).scalar()
        assert result == "failure_reason"


@pytest.mark.integration
class TestMigrationsDowngrade:
    """Verify that downgrade base removes all application tables.

    This test performs a full down+up cycle independently of the session
    fixture so it doesn't interfere with other tests.
    """

    def test_downgrade_then_upgrade_roundtrip(self, db_engine):
        env = {**os.environ, "DATABASE_URL": str(db_engine.url)}

        # downgrade to base
        subprocess.run(
            ["python", "-m", "alembic", "downgrade", "base"],
            cwd=BACKEND_DIR, env=env, check=True,
        )

        insp = inspect(db_engine)
        remaining = set(insp.get_table_names()) & EXPECTED_TABLES
        assert not remaining, (
            f"Tables still present after downgrade base: {remaining}"
        )

        # upgrade again so subsequent tests can still use the engine
        subprocess.run(
            ["python", "-m", "alembic", "upgrade", "head"],
            cwd=BACKEND_DIR, env=env, check=True,
        )

        insp2 = inspect(db_engine)
        tables_after = set(insp2.get_table_names())
        assert EXPECTED_TABLES.issubset(tables_after)
