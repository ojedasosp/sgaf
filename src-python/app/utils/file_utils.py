"""File and path utilities for SGAF.

DB path and export folder operations — centralises all OS path logic.
"""

import os


def safe_export_file(path: str, content: bytes) -> None:
    """Write binary content to a file path.

    Args:
        path: Absolute or relative file path to write to.
        content: Binary content to write.

    Raises:
        ValueError: If path is empty or parent directory does not exist.
        OSError: If write fails (permissions, disk full, etc.).
    """
    if not path:
        raise ValueError("path must be non-empty")
    parent = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(parent):
        raise ValueError(f"Parent directory does not exist: {parent}")
    with open(path, "wb") as f:
        f.write(content)


def get_app_data_dir() -> str:
    """Return the SGAF app data directory from the SGAF_DB_PATH env var.

    The directory is the parent of sgaf.db (e.g. '{AppData}/sgaf/').

    Raises RuntimeError if SGAF_DB_PATH is not set.
    """
    db_path = os.environ.get("SGAF_DB_PATH", "")
    if not db_path:
        raise RuntimeError(
            "SGAF_DB_PATH environment variable is not set. "
            "Ensure the Tauri sidecar passes the DB path on startup."
        )
    return os.path.dirname(db_path)
