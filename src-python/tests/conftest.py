"""Pytest fixtures for SGAF tests.

Provides in-memory SQLite engine and Flask test client with DB initialized.
"""

from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text

from migrations.runner import run_migrations


def _make_engine_with_fk():
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    return engine


@pytest.fixture
def test_engine():
    """In-memory SQLite engine with all migrations applied and FK enforcement."""
    engine = _make_engine_with_fk()
    run_migrations(engine)
    return engine


@pytest.fixture
def test_engine_pre_009():
    """In-memory SQLite engine with migrations 001–008 applied (pre-009 schema).

    Used by data-preservation tests that need to insert rows at the pre-009
    schema version and then apply migration 009 on top to verify the AC1
    upgrade scenario.
    """
    engine = _make_engine_with_fk()
    migrations_dir = Path(__file__).resolve().parent.parent / "migrations"

    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE IF NOT EXISTS schema_version (
                    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
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
                    "VALUES (:name, :ts)"
                ),
                {"name": sql_file.name, "ts": "2026-04-12T00:00:00Z"},
            )

    return engine


@pytest.fixture
def test_client(test_engine, monkeypatch):
    """Flask test client backed by an in-memory SQLite database."""
    import app.database as db_module

    monkeypatch.setattr(db_module, "_engine", test_engine)
    monkeypatch.setenv("SGAF_DB_PATH", ":memory:")

    from app import create_app

    flask_app = create_app()
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as client:
        yield client
