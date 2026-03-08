"""Pytest fixtures for SGAF tests.

Provides in-memory SQLite engine and Flask test client with DB initialized.
"""

import pytest
from sqlalchemy import create_engine, event

from migrations.runner import run_migrations


@pytest.fixture
def test_engine():
    """In-memory SQLite engine with all migrations applied and FK enforcement."""
    engine = create_engine("sqlite:///:memory:", connect_args={"check_same_thread": False})

    @event.listens_for(engine, "connect")
    def _set_sqlite_pragma(dbapi_conn, connection_record):
        cursor = dbapi_conn.cursor()
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.close()

    run_migrations(engine)
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
