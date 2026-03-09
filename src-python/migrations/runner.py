"""Versioned SQL migration runner for SGAF.

Reads schema_version table, applies any pending .sql scripts in numeric order.
Each script runs in its own transaction — idempotent and safe to re-run.
"""

from datetime import datetime, timezone
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.engine import Engine

import sys

# PyInstaller extracts data files to sys._MEIPASS; in dev, use the file's directory
_BASE = Path(getattr(sys, "_MEIPASS", Path(__file__).parent.parent))
MIGRATIONS_DIR = _BASE / "migrations"


def run_migrations(engine: Engine) -> None:
    """Apply pending SQL migration scripts in order. Idempotent."""
    with engine.begin() as conn:
        conn.execute(text("""
                CREATE TABLE IF NOT EXISTS schema_version (
                    version_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    script_name TEXT NOT NULL UNIQUE,
                    applied_at TEXT NOT NULL
                )
            """))

    sql_files = sorted(MIGRATIONS_DIR.glob("*.sql"))

    for sql_file in sql_files:
        script_name = sql_file.name

        with engine.connect() as conn:
            already_applied = conn.execute(
                text("SELECT 1 FROM schema_version WHERE script_name = :name"),
                {"name": script_name},
            ).fetchone()

        if already_applied is not None:
            continue

        sql_content = sql_file.read_text(encoding="utf-8")
        applied_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

        with engine.begin() as conn:
            for statement in sql_content.split(";"):
                stmt = statement.strip()
                if stmt:
                    conn.execute(text(stmt))
            conn.execute(
                text("INSERT INTO schema_version (script_name, applied_at) " "VALUES (:name, :ts)"),
                {"name": script_name, "ts": applied_at},
            )
