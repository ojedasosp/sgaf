"""File and path utilities for SGAF.

DB path and export folder operations — centralises all OS path logic.
"""

import os


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
