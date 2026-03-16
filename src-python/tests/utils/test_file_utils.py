"""Tests for file_utils — OS path utilities."""

import os

import pytest

from app.utils.file_utils import get_app_data_dir, safe_export_file


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


# ---------------------------------------------------------------------------
# safe_export_file
# ---------------------------------------------------------------------------


class TestSafeExportFile:
    def test_writes_binary_content(self, tmp_path):
        target = tmp_path / "output.pdf"
        safe_export_file(str(target), b"%PDF-fake-content")
        assert target.read_bytes() == b"%PDF-fake-content"

    def test_raises_on_empty_path(self):
        with pytest.raises(ValueError, match="non-empty"):
            safe_export_file("", b"data")

    def test_raises_when_parent_dir_missing(self, tmp_path):
        bad_path = str(tmp_path / "nonexistent_dir" / "file.pdf")
        with pytest.raises(ValueError, match="Parent directory does not exist"):
            safe_export_file(bad_path, b"data")

    def test_propagates_os_error_on_permission_failure(self, tmp_path):
        target = tmp_path / "readonly_dir" / "file.pdf"
        target.parent.mkdir()
        target.parent.chmod(0o000)
        try:
            with pytest.raises(OSError):
                safe_export_file(str(target), b"data")
        finally:
            target.parent.chmod(0o755)

    def test_overwrites_existing_file(self, tmp_path):
        target = tmp_path / "output.pdf"
        target.write_bytes(b"old")
        safe_export_file(str(target), b"new")
        assert target.read_bytes() == b"new"
