"""Tests for database.py — engine creation and error handling."""

import pytest
from sqlalchemy import text


def test_get_engine_raises_when_pg_vars_missing(monkeypatch):
    """Clear error when required PG_* vars are not set."""
    import app.database as db_module

    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr("app.config.Config.PG_HOST", "")

    with pytest.raises(RuntimeError, match="Missing required environment variables"):
        db_module.get_engine()


def test_get_engine_raises_when_db_unreachable(monkeypatch):
    """Clear error when PostgreSQL server cannot be reached."""
    import app.database as db_module

    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr("app.config.Config.PG_HOST", "nonexistent.invalid.host")
    monkeypatch.setattr("app.config.Config.PG_USER", "user")
    monkeypatch.setattr("app.config.Config.PG_PASS", "pass")
    monkeypatch.setattr("app.config.Config.PG_DB", "db")

    with pytest.raises(RuntimeError, match="Cannot connect to PostgreSQL"):
        db_module.get_engine()


def test_get_db_is_context_manager(test_engine, monkeypatch):
    """get_db() must work as a context manager and return a live connection."""
    import app.database as db_module

    monkeypatch.setattr(db_module, "_engine", test_engine)

    with db_module.get_db() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        assert result == 1
