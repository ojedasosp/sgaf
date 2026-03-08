"""Tests for database.py — engine creation, error handling, FK enforcement."""

import pytest
from sqlalchemy import text


def test_get_engine_raises_when_db_path_empty(monkeypatch):
    """AC5: Clear error when SGAF_DB_PATH is not set."""
    import app.database as db_module

    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr("app.config.Config.DB_PATH", "")

    with pytest.raises(RuntimeError, match="SGAF_DB_PATH"):
        db_module.get_engine()


def test_get_engine_raises_when_db_unreachable(monkeypatch):
    """AC5: Clear error when DB path directory does not exist."""
    import app.database as db_module

    monkeypatch.setattr(db_module, "_engine", None)
    monkeypatch.setattr("app.config.Config.DB_PATH", "/nonexistent/path/sgaf.db")

    with pytest.raises(RuntimeError, match="Cannot open SQLite database"):
        db_module.get_engine()


def test_get_db_is_context_manager(test_engine, monkeypatch):
    """get_db() must work with 'with' statement."""
    import app.database as db_module

    monkeypatch.setattr(db_module, "_engine", test_engine)

    with db_module.get_db() as conn:
        result = conn.execute(text("SELECT 1")).scalar()
        assert result == 1


def test_foreign_keys_enforced(test_engine, monkeypatch):
    """M1: PRAGMA foreign_keys=ON is set on every connection."""
    import app.database as db_module

    monkeypatch.setattr(db_module, "_engine", test_engine)

    with db_module.get_db() as conn:
        fk_status = conn.execute(text("PRAGMA foreign_keys")).scalar()
        assert fk_status == 1, "Foreign key enforcement is OFF — expected ON"
