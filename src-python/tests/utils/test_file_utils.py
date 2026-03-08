"""Tests for file_utils — OS path utilities."""

import pytest

from app.utils.file_utils import get_app_data_dir


def test_returns_parent_of_db_path(monkeypatch):
    monkeypatch.setenv("SGAF_DB_PATH", "/home/user/.local/share/com.sgaf.app/sgaf/sgaf.db")
    assert get_app_data_dir() == "/home/user/.local/share/com.sgaf.app/sgaf"


def test_raises_when_env_not_set(monkeypatch):
    monkeypatch.delenv("SGAF_DB_PATH", raising=False)
    with pytest.raises(RuntimeError, match="SGAF_DB_PATH"):
        get_app_data_dir()


def test_raises_when_env_empty(monkeypatch):
    monkeypatch.setenv("SGAF_DB_PATH", "")
    with pytest.raises(RuntimeError, match="SGAF_DB_PATH"):
        get_app_data_dir()
