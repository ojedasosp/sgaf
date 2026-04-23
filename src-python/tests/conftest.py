"""Pytest fixtures for SGAF tests.

Requires TEST_DATABASE_URL env var pointing to a PostgreSQL test database, e.g.:
  TEST_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/sgaf_test

For the pre-009 upgrade test, also set:
  TEST_PRE_009_DATABASE_URL=postgresql+psycopg2://user:pass@localhost:5432/sgaf_pre009_test
(must be a separate, clean database — the test applies migration 009 manually)
"""

import os
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from migrations.runner import run_migrations


def _require_url(var: str) -> str:
    url = os.environ.get(var, "")
    if not url:
        pytest.skip(f"{var} not set — skipping DB tests")
    return url


@pytest.fixture(scope="session")
def test_engine():
    """PostgreSQL engine with all migrations applied. Shared across the test session."""
    engine = create_engine(_require_url("TEST_DATABASE_URL"))
    run_migrations(engine)
    return engine


@pytest.fixture(scope="session")
def test_engine_pre_009():
    """PostgreSQL engine with migrations 001–008 applied (pre-009 schema).

    Uses TEST_PRE_009_DATABASE_URL — must be a separate clean database.
    """
    engine = create_engine(_require_url("TEST_PRE_009_DATABASE_URL"))
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version_id SERIAL PRIMARY KEY,
                    script_name TEXT NOT NULL UNIQUE,
                    applied_at TEXT NOT NULL
                )
                """
            )
        )

    for sql_file in sorted(migrations_dir.glob("*.sql")):
        version = int(sql_file.name[:3])
        if version >= 9:
            continue
        sql_content = sql_file.read_text(encoding="utf-8")
        with engine.begin() as conn:
            for statement in sql_content.split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(text(stmt))
            conn.execute(
                text(
                    "INSERT INTO schema_version (script_name, applied_at) "
                    "VALUES (:name, :ts) ON CONFLICT (script_name) DO NOTHING"
                ),
                {"name": sql_file.name, "ts": "2026-04-22T00:00:00Z"},
            )

    return engine


@pytest.fixture
def test_client(test_engine, monkeypatch):
    """Flask test client backed by the test PostgreSQL database."""
    import app.database as db_module

    monkeypatch.setattr(db_module, "_engine", test_engine)
    monkeypatch.setenv("PG_HOST", "localhost")
    monkeypatch.setenv("PG_PORT", "5432")
    monkeypatch.setenv("PG_USER", "test")
    monkeypatch.setenv("PG_PASS", "test")
    monkeypatch.setenv("PG_DB", "sgaf_test")

    from app import create_app

    flask_app = create_app()
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client
