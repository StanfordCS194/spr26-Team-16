"""Pytest fixtures for backend integration tests.

Requires a running Postgres with the pgvector extension available.
Set DATABASE_URL in the environment (default: localhost test DB).

The fixture flow per test session:
  1. Apply sql/auth_stub.sql (creates auth schema + auth.uid() stub)
  2. Run `alembic upgrade head`
  3. Load fixture dataset via gen_fixtures
  4. Yield
  5. Run `alembic downgrade base`
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import psycopg
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session

BACKEND_DIR = Path(__file__).parent.parent
AUTH_STUB_SQL = BACKEND_DIR / "sql" / "auth_stub.sql"

DEFAULT_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/contexthub_test"
DEFAULT_PSYCOPG_URL = "postgresql://postgres:postgres@localhost:5432/contexthub_test"


def _psycopg_url() -> str:
    raw = os.environ.get("DATABASE_URL", DEFAULT_URL)
    # Convert SQLAlchemy URL scheme to psycopg3 native URL
    return raw.replace("postgresql+psycopg://", "postgresql://")


def _alembic_url() -> str:
    return os.environ.get("DATABASE_URL", DEFAULT_URL)


@pytest.fixture(scope="session")
def db_url() -> str:
    return _alembic_url()


@pytest.fixture(scope="session")
def db_engine(db_url: str):
    """Session-scoped engine: applies auth stub, runs migrations, loads fixtures."""
    engine = create_engine(db_url, pool_pre_ping=True)

    # 1. Apply auth stub (idempotent)
    with psycopg.connect(_psycopg_url(), autocommit=True) as conn:
        conn.execute(AUTH_STUB_SQL.read_text())

    # 2. Migrate up
    env = {**os.environ, "DATABASE_URL": db_url}
    subprocess.run(
        ["python", "-m", "alembic", "upgrade", "head"],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
    )

    # 3. Load fixture dataset
    from scripts.gen_fixtures import generate
    generate(db_url)

    yield engine

    # 4. Migrate down
    subprocess.run(
        ["python", "-m", "alembic", "downgrade", "base"],
        cwd=BACKEND_DIR,
        env=env,
        check=True,
    )

    engine.dispose()


@pytest.fixture
def db_session(db_engine):
    """Function-scoped session — rolls back after each test."""
    with Session(db_engine) as session:
        with session.begin():
            yield session
            session.rollback()


@pytest.fixture
def raw_conn():
    """Raw psycopg3 connection for RLS tests (role/GUC switching)."""
    with psycopg.connect(_psycopg_url()) as conn:
        yield conn
